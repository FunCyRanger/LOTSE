CFLAGS := -Wall -Wextra -Werror -Wno-unused-parameter -Wno-unused-function -Wno-unused-variable -g -O0
INCLUDES := -I. -Imocks -I../main -Ivendor/cjson

SRCS := test_transform.c unity.c ../main/transform.c ../main/lotse_config.c vendor/cjson/cJSON.c

test_transform: $(SRCS)
	gcc $(CFLAGS) $(INCLUDES) -o $@ $^ -lm

run: test_transform
	./test_transform

clean:
	rm -f test_transform

.PHONY: run clean
