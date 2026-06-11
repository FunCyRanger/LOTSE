#include <string.h>
#include <stdlib.h>
#include <stdio.h>
#include <time.h>
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "esp_log.h"
#include "esp_timer.h"
#include "lwip/sockets.h"
#include "lwip/netdb.h"
#include "cJSON.h"
#include "mqtt_broker.h"
#include "lotse_config.h"

static const char *TAG = "mqtt_broker";

#define MAX_CLIENTS  MAX_MQTT_CLIENTS
#define BUF_SIZE     2048
#define LOG_ENTRIES  200

typedef struct {
    char client_id[64];
    char topic[128];
    char payload[65];
    int64_t time_us;
    char time_str[20];
} log_entry_t;

static log_entry_t s_log[LOG_ENTRIES];
static int s_log_head = 0;
static int s_log_count = 0;

typedef struct mqtt_sub {
    char topic[128];
    struct mqtt_sub *next;
} mqtt_sub_t;

typedef struct mqtt_client {
    int fd;
    bool in_use;
    char client_id[64];
    mqtt_sub_t *subscriptions;
    bool connected;
    uint8_t buf[BUF_SIZE];
    int buf_len;
} mqtt_client_t;

static mqtt_client_t s_clients[MAX_CLIENTS];
static int s_server_fd = -1;
static mqtt_publish_cb_t s_publish_cb = NULL;
static mqtt_connect_cb_t s_connect_cb = NULL;

static mqtt_client_t *client_alloc(void)
{
    for (int i = 0; i < MAX_CLIENTS; i++) {
        if (!s_clients[i].in_use) {
            memset(&s_clients[i], 0, sizeof(mqtt_client_t));
            s_clients[i].in_use = true;
            s_clients[i].fd = -1;
            return &s_clients[i];
        }
    }
    return NULL;
}

static void client_free(mqtt_client_t *c)
{
    if (c->fd >= 0) { close(c->fd); c->fd = -1; }
    mqtt_sub_t *s = c->subscriptions;
    while (s) { mqtt_sub_t *next = s->next; free(s); s = next; }
    memset(c, 0, sizeof(*c));
}

static int read_remaining_length(const uint8_t *buf, int *bytes)
{
    int multiplier = 1;
    int value = 0;
    int i = 0;
    do {
        if (i > 3) return -1;
        value += (buf[i] & 0x7F) * multiplier;
        multiplier *= 128;
    } while ((buf[i++] & 0x80) && i < 4);
    *bytes = i;
    return value;
}

static int write_remaining_length(uint8_t *buf, int len)
{
    int i = 0;
    do {
        uint8_t b = len % 128;
        len /= 128;
        if (len > 0) b |= 0x80;
        buf[i++] = b;
    } while (len > 0);
    return i;
}

static bool topic_matches(const char *filter, const char *topic)
{
    while (*filter && *topic) {
        if (*filter == '+') {
            filter++;
            while (*topic && *topic != '/') topic++;
        } else if (*filter == '#') {
            return true;
        } else if (*filter != *topic) {
            return false;
        } else {
            filter++;
            topic++;
        }
    }
    return (*filter == '\0' && *topic == '\0') ||
           (*filter == '#' && *(filter+1) == '\0');
}

static void forward_publish(const char *topic, const uint8_t *payload,
                            int payload_len, mqtt_client_t *exclude)
{
    for (int i = 0; i < MAX_CLIENTS; i++) {
        mqtt_client_t *c = &s_clients[i];
        if (!c->in_use || !c->connected || c == exclude) continue;
        mqtt_sub_t *sub = c->subscriptions;
        while (sub) {
            if (topic_matches(sub->topic, topic)) break;
            sub = sub->next;
        }
        if (!sub) continue;

        int topic_len = strlen(topic);
        uint8_t header[4];
        int hdr_sz = 1;
        int remaining = 2 + topic_len + payload_len;
        if (remaining > 127) hdr_sz++;
        if (remaining > 16383) hdr_sz++;
        header[0] = 0x30;
        int rl_sz = write_remaining_length(header + 1, remaining);

        uint8_t *packet = malloc(1 + rl_sz + 2 + topic_len + payload_len);
        if (!packet) continue;
        int pos = 0;
        packet[pos++] = 0x30;
        pos += write_remaining_length(packet + pos, remaining);
        packet[pos++] = (uint8_t)(topic_len >> 8);
        packet[pos++] = (uint8_t)(topic_len & 0xFF);
        memcpy(packet + pos, topic, topic_len);
        pos += topic_len;
        memcpy(packet + pos, payload, payload_len);
        pos += payload_len;

        write(c->fd, packet, pos);
        free(packet);
    }
}

static void handle_publish(mqtt_client_t *client, const uint8_t *buf, int len)
{
    if (len < 2) return;
    int topic_len = (buf[0] << 8) | buf[1];
    if (len < 2 + topic_len) return;

    char topic[128] = {0};
    int tlen = topic_len < 127 ? topic_len : 127;
    memcpy(topic, buf + 2, tlen);
    topic[tlen] = 0;

    int payload_len = len - 2 - topic_len;
    const uint8_t *payload = buf + 2 + topic_len;

    static int s_publish_count = 0;
    static int64_t s_last_publish_us = 0;
    s_publish_count++;
    int64_t now = esp_timer_get_time();
    if (s_last_publish_us > 0 && (now - s_last_publish_us) > 30000000) {
        ESP_LOGW(TAG, "WATCHDOG: %lld ms since last publish (count=%d)",
                 (now - s_last_publish_us) / 1000, s_publish_count);
    }
    s_last_publish_us = now;
    if (s_publish_count % 10 == 0) {
        ESP_LOGI(TAG, "PUBLISH #%d: topic=%s, client=%s", s_publish_count, topic, client->client_id);
    }

    ESP_LOGI(TAG, "PUBLISH %s from %s (payload_len=%d)", topic, client->client_id, payload_len);
    if (payload_len > 0) {
        char preview[65];
        int plen = payload_len < 64 ? payload_len : 64;
        memcpy(preview, payload, plen);
        preview[plen] = 0;
        ESP_LOGI(TAG, "  payload: %s", preview);
    }

    // Store in ring buffer
    {
        log_entry_t *e = &s_log[s_log_head];
        strncpy(e->client_id, client->client_id, sizeof(e->client_id)-1);
        strncpy(e->topic, topic, sizeof(e->topic)-1);
        int plen = payload_len < 64 ? payload_len : 64;
        memcpy(e->payload, payload, plen);
        e->payload[plen] = 0;
        e->time_us = esp_timer_get_time();
        time_t now = time(NULL);
        struct tm *tm_info = localtime(&now);
        if (tm_info && tm_info->tm_year >= (2024 - 1900)) {
            strftime(e->time_str, sizeof(e->time_str), "%H:%M:%S", tm_info);
        } else {
            e->time_str[0] = '\0';
        }
        s_log_head = (s_log_head + 1) % LOG_ENTRIES;
        if (s_log_count < LOG_ENTRIES) s_log_count++;
    }

    forward_publish(topic, payload, payload_len, client);

    if (s_publish_cb) {
        char payload_str[512];
        int plen = payload_len < 511 ? payload_len : 511;
        memcpy(payload_str, payload, plen);
        payload_str[plen] = 0;
        s_publish_cb(topic, payload_str, payload_len);
    }
}

static void handle_subscribe(mqtt_client_t *client, const uint8_t *buf, int len)
{
    if (len < 2) return;
    int pkt_id = (buf[0] << 8) | buf[1];
    int pos = 2;
    int topic_count = 0;
    while (pos < len) {
        if (pos + 2 > len) break;
        int topic_len = (buf[pos] << 8) | buf[pos+1];
        pos += 2;
        if (pos + topic_len + 1 > len) break;
        char topic[128];
        int tlen = topic_len < 127 ? topic_len : 127;
        memcpy(topic, buf + pos, tlen);
        topic[tlen] = 0;
        pos += topic_len;
        uint8_t qos = buf[pos++];
        topic_count++;

        mqtt_sub_t *sub = malloc(sizeof(mqtt_sub_t));
        if (sub) {
            strncpy(sub->topic, topic, sizeof(sub->topic)-1);
            sub->next = client->subscriptions;
            client->subscriptions = sub;
            ESP_LOGI(TAG, "SUB %s (qos=%d)", topic, qos);
        }
    }

    int suback_len = 2 + topic_count;
    if (suback_len > 255) suback_len = 255;
    uint8_t *suback = malloc(1 + 1 + suback_len); // fixed header + remaining + packet_id + return_codes
    if (!suback) return;
    suback[0] = 0x90;
    suback[1] = suback_len;
    suback[2] = buf[0];
    suback[3] = buf[1];
    for (int i = 0; i < topic_count && i < 253; i++)
        suback[4 + i] = 0x00;
    write(client->fd, suback, 2 + suback_len);
    free(suback);
}

static void handle_packet(mqtt_client_t *client, const uint8_t *buf, int len)
{
    if (len < 2) return;
    uint8_t type = buf[0] & 0xF0;

    int rl_bytes;
    int remaining = read_remaining_length(buf + 1, &rl_bytes);
    if (remaining < 0) return;

    int header_len = 1 + rl_bytes;
    if (header_len + remaining > len) return;

    const uint8_t *data = buf + header_len;

    switch (type) {
    case 0x10: { // CONNECT
        int pos = 0;
        if (remaining < 6) return;
        int prot_len = (data[pos] << 8) | data[pos+1];
        pos += 2 + prot_len;
        if (pos + 1 > remaining) return;
        // Skip protocol level (1) + connect flags (1) + keepalive (2)
        pos += 4;
        // Client ID
        if (pos + 2 > remaining) return;
        int cid_len = (data[pos] << 8) | data[pos+1];
        pos += 2;
        int clen = cid_len < 63 ? cid_len : 63;
        memcpy(client->client_id, data + pos, clen);
        client->client_id[clen] = 0;

        client->connected = true;
        uint8_t connack[4] = {0x20, 0x02, 0x00, 0x00};
        int wlen = write(client->fd, connack, 4);
        if (wlen != 4) {
            ESP_LOGW(TAG, "CONNACK write failed for %s (ret=%d, errno=%d)", client->client_id, wlen, errno);
        }
        ESP_LOGI(TAG, "CONNECT %s", client->client_id);
        if (s_connect_cb) s_connect_cb(client->client_id);
        break;
    }
    case 0x30: // PUBLISH
        handle_publish(client, data, remaining);
        break;
    case 0x50: { // PUBREL (QoS 2)
        uint8_t pubcomp[4] = {0x60, 0x02, data[0], data[1]};
        write(client->fd, pubcomp, 4);
        break;
    }
    case 0x80: // SUBSCRIBE
        handle_subscribe(client, data, remaining);
        break;
    case 0xA0: { // UNSUBSCRIBE
        uint8_t unsuback[4] = {0xB0, 0x02, data[0], data[1]};
        write(client->fd, unsuback, 4);
        break;
    }
    case 0xC0: { // PINGREQ
        uint8_t pingresp[2] = {0xD0, 0x00};
        write(client->fd, pingresp, 2);
        break;
    }
    case 0xE0: // DISCONNECT
        client->connected = false;
        break;
    }
}

static void mqtt_broker_task(void *pvParameter)
{
    struct sockaddr_in addr = {
        .sin_family = AF_INET,
        .sin_port = htons(MQTT_BROKER_PORT),
        .sin_addr.s_addr = htonl(INADDR_ANY),
    };

    s_server_fd = socket(AF_INET, SOCK_STREAM, IPPROTO_TCP);
    if (s_server_fd < 0) {
        ESP_LOGE(TAG, "socket failed");
        vTaskDelete(NULL);
    }

    int opt = 1;
    setsockopt(s_server_fd, SOL_SOCKET, SO_REUSEADDR, &opt, sizeof(opt));

    if (bind(s_server_fd, (struct sockaddr *)&addr, sizeof(addr)) < 0) {
        ESP_LOGE(TAG, "bind failed");
        close(s_server_fd);
        vTaskDelete(NULL);
    }

    if (listen(s_server_fd, 5) < 0) {
        ESP_LOGE(TAG, "listen failed");
        close(s_server_fd);
        vTaskDelete(NULL);
    }

    ESP_LOGI(TAG, "MQTT broker listening on port %d", MQTT_BROKER_PORT);

    while (1) {
        fd_set readfds;
        FD_ZERO(&readfds);
        FD_SET(s_server_fd, &readfds);
        int max_fd = s_server_fd;

        for (int i = 0; i < MAX_CLIENTS; i++) {
            if (s_clients[i].in_use && s_clients[i].fd >= 0) {
                FD_SET(s_clients[i].fd, &readfds);
                if (s_clients[i].fd > max_fd) max_fd = s_clients[i].fd;
            }
        }

        struct timeval tv = { .tv_sec = 1, .tv_usec = 0 };
        int rc = select(max_fd + 1, &readfds, NULL, NULL, &tv);
        if (rc < 0) continue;

        if (FD_ISSET(s_server_fd, &readfds)) {
            struct sockaddr_in client_addr;
            socklen_t addr_len = sizeof(client_addr);
            int client_fd = accept(s_server_fd, (struct sockaddr *)&client_addr, &addr_len);
            if (client_fd >= 0) {
                mqtt_client_t *c = client_alloc();
                if (c) {
                    c->fd = client_fd;
                    struct timeval snd_tv = { .tv_sec = 1, .tv_usec = 0 };
                    setsockopt(client_fd, SOL_SOCKET, SO_SNDTIMEO, &snd_tv, sizeof(snd_tv));
                    char remote_ip[16];
                    inet_ntop(AF_INET, &client_addr.sin_addr, remote_ip, sizeof(remote_ip));
                    ESP_LOGI(TAG, "new client fd=%d from %s:%d", client_fd, remote_ip, ntohs(client_addr.sin_port));
                } else {
                    close(client_fd);
                    ESP_LOGW(TAG, "max clients reached, rejected");
                }
            }
        }

        for (int i = 0; i < MAX_CLIENTS; i++) {
            mqtt_client_t *c = &s_clients[i];
            if (!c->in_use || c->fd < 0) continue;
            if (!FD_ISSET(c->fd, &readfds)) continue;

            uint8_t tmp[BUF_SIZE];
            int n = read(c->fd, tmp, sizeof(tmp));
            if (n <= 0) {
                ESP_LOGI(TAG, "client %s disconnected", c->client_id);
                client_free(c);
                continue;
            }

            // Append to persistent buffer
            if (n + c->buf_len > BUF_SIZE) {
                int room = BUF_SIZE - c->buf_len;
                if (room > 0) {
                    memcpy(c->buf + c->buf_len, tmp, room);
                    c->buf_len = BUF_SIZE;
                    ESP_LOGW(TAG, "buffer full for %s, dropped %d bytes", c->client_id, n - room);
                } else {
                    ESP_LOGW(TAG, "buffer full for %s, dropped %d bytes", c->client_id, n);
                }
            } else {
                memcpy(c->buf + c->buf_len, tmp, n);
                c->buf_len += n;
            }

            int offset = 0;
            int pkt_num = 0;
            while (offset < c->buf_len) {
                int remaining = 0;
                int rl_bytes = 0;
                if (offset + 1 < c->buf_len) {
                    remaining = read_remaining_length(c->buf + offset + 1, &rl_bytes);
                }
                if (remaining < 0) break;
                int pkt_len = 1 + rl_bytes + remaining;
                if (pkt_len > c->buf_len - offset) break;
                handle_packet(c, c->buf + offset, pkt_len);
                offset += pkt_len;
                pkt_num++;
            }
            if (pkt_num > 0) {
                ESP_LOGI(TAG, "READ: %d new bytes, %d packets from %s", n, pkt_num, c->client_id);
            }
            if (offset < c->buf_len) {
                int leftover = c->buf_len - offset;
                ESP_LOGD(TAG, "PARTIAL: %d bytes remain for %s", leftover, c->client_id);
                memmove(c->buf, c->buf + offset, leftover);
                c->buf_len = leftover;
            } else {
                c->buf_len = 0;
            }
        }
    }
}

esp_err_t mqtt_broker_start(void)
{
    memset(s_clients, 0, sizeof(s_clients));
    xTaskCreate(mqtt_broker_task, "mqtt_broker", 16384, NULL, 5, NULL);
    return ESP_OK;
}

void mqtt_broker_set_publish_callback(mqtt_publish_cb_t cb)
{
    s_publish_cb = cb;
}

void mqtt_broker_set_connect_callback(mqtt_connect_cb_t cb)
{
    s_connect_cb = cb;
}

int mqtt_broker_client_count(void)
{
    int count = 0;
    for (int i = 0; i < MAX_CLIENTS; i++) {
        if (s_clients[i].in_use && s_clients[i].connected) count++;
    }
    return count;
}

esp_err_t mqtt_broker_publish(const char *topic, const char *payload, int retain)
{
    forward_publish(topic, (const uint8_t *)payload, strlen(payload), NULL);
    return ESP_OK;
}

static void sanitize_str(char *buf, size_t len)
{
    for (size_t i = 0; i < len && buf[i]; i++) {
        if ((unsigned char)buf[i] < 0x20 || (unsigned char)buf[i] >= 0x7F)
            buf[i] = '.';
    }
}

char *mqtt_broker_get_log_json(void)
{
    cJSON *arr = cJSON_CreateArray();
    if (!arr) return NULL;

    int total = s_log_count < LOG_ENTRIES ? s_log_count : LOG_ENTRIES;
    for (int i = 0; i < total; i++) {
        int idx = (s_log_head - total + i + LOG_ENTRIES) % LOG_ENTRIES;
        log_entry_t *e = &s_log[idx];
        cJSON *item = cJSON_CreateObject();
        char client_copy[sizeof(e->client_id)];
        char topic_copy[sizeof(e->topic)];
        char payload_copy[sizeof(e->payload)];
        strncpy(client_copy, e->client_id, sizeof(client_copy)-1);
        strncpy(topic_copy, e->topic, sizeof(topic_copy)-1);
        strncpy(payload_copy, e->payload, sizeof(payload_copy)-1);
        client_copy[sizeof(client_copy)-1] = '\0';
        topic_copy[sizeof(topic_copy)-1] = '\0';
        payload_copy[sizeof(payload_copy)-1] = '\0';
        sanitize_str(client_copy, sizeof(client_copy));
        sanitize_str(topic_copy, sizeof(topic_copy));
        sanitize_str(payload_copy, sizeof(payload_copy));
        cJSON_AddStringToObject(item, "client", client_copy);
        cJSON_AddStringToObject(item, "topic", topic_copy);
        cJSON_AddStringToObject(item, "payload", payload_copy);
        cJSON_AddNumberToObject(item, "time", (double)e->time_us / 1000000.0);
        cJSON_AddStringToObject(item, "time_str", e->time_str[0] ? e->time_str : "");
        cJSON_AddItemToArray(arr, item);
    }

    char *json = cJSON_PrintUnformatted(arr);
    cJSON_Delete(arr);
    return json;
}
