#pragma once

static const char *SMI_3_LINE =
    "1,1@1,Strombezug gesamt,Wh,E_total,0\n"
    "1,1@1,Aktuelle Leistung,W,Power,1\n"
    "1,1@1,Spannung L1,V,Voltage_L1,1\n";

static const char *SMI_WITH_BATTERY =
    "1,1@1,Grid Power,W,Power,1\n"
    "1,1@1,Grid Energy In,Wh,E_in,1\n"
    "1,1@1,Grid Energy Out,Wh,E_out,1\n"
    "1,1@1,Battery SoC,%,BatteryPct,0\n"
    "1,1@1,Battery Power,W,BatteryPower,1\n"
    "1,1@1,Solar Power,W,SolarPower,1\n";

static const char *SMI_18_LINE =
    "1,1@1,Bezug Total Wirkarbeit Wh,Wh,Total_Bezug,0\n"
    "1,1@1,Total Wirkarbeit alle Phasen,W,Total_Wirkleistung,1\n"
    "1,1@1,Spannung L1,V,Spannung_L1,1\n"
    "1,1@1,Spannung L2,V,Spannung_L2,1\n"
    "1,1@1,Spannung L3,V,Spannung_L3,1\n"
    "1,1@1,Strom L1,A,Strom_L1,1\n"
    "1,1@1,Strom L2,A,Strom_L2,1\n"
    "1,1@1,Strom L3,A,Strom_L3,1\n"
    "1,1@1,Wirkleistung L1,W,Wirkleistung_L1,1\n"
    "1,1@1,Wirkleistung L2,W,Wirkleistung_L2,1\n"
    "1,1@1,Wirkleistung L3,W,Wirkleistung_L3,1\n"
    "1,1@1,Wirkleistung Bezug L1,W,Bezug_L1,1\n"
    "1,1@1,Wirkleistung Bezug L2,W,Bezug_L2,1\n"
    "1,1@1,Wirkleistung Bezug L3,W,Bezug_L3,1\n"
    "1,1@1,Total effect. energy,MWh,E_total,0\n"
    "1,1@1,Current power,kW,Power_kW,1\n"
    "1,1@1,Frequency,Hz,Frequency,2\n"
    "1,1@1,Power factor,,CosPhi,2\n";

static const char *SMI_EMPTY = "";

static const char *SMI_MALFORMED = "1,foo,bar\n";

static const char *SMI_NO_UNIT =
    "1,1@1,Power factor,,CosPhi,2\n";

static const char *TASMOTA_JSON_BASIC =
    "{\"SML1\":{"
    "\"Total_Bezug\":1234.5,"
    "\"Total_Wirkleistung\":-1200,"
    "\"Spannung_L1\":230.1"
    "}}";

static const char *TASMOTA_JSON_ALL_TYPES =
    "{\"SML1\":{"
    "\"Power\":1200,"
    "\"E_in\":2500,"
    "\"E_out\":800,"
    "\"BatteryPct\":85,"
    "\"BatteryPower\":-500,"
    "\"SolarPower\":3500"
    "}}";

static const char *TASMOTA_JSON_BS_CLAMP =
    "{\"SML1\":{\"BatteryPct\":-5}}";

static const char *TASMOTA_JSON_BS_CLAMP_HIGH =
    "{\"SML1\":{\"BatteryPct\":150}}";

static const char *TASMOTA_JSON_ENERGY_NEGATIVE =
    "{\"SML1\":{\"E_in\":-100}}";

static const char *TASMOTA_JSON_POWER_OVER =
    "{\"SML1\":{\"Power\":600000}}";

static const char *TASMOTA_JSON_POWER_UNDER =
    "{\"SML1\":{\"Power\":-600000}}";

static const char *TASMOTA_JSON_EMPTY_METER =
    "{\"SML1\":{}}";

static const char *TASMOTA_JSON_NO_METER =
    "{\"other\":42}";

static const char *TASMOTA_JSON_INVALID =
    "not json";

/* Dedup test fixtures */
static const char *SMI_3_POWER =
    "1,1@1,Total Power,W,Total_Power,1\n"
    "1,1@1,Phase 1 Power,W,Phase1_Power,1\n"
    "1,1@1,Phase 2 Power,W,Phase2_Power,1\n";

static const char *SMI_5_POWER =
    "1,1@1,Power A,W,Power_A,1\n"
    "1,1@1,Power B,W,Power_B,1\n"
    "1,1@1,Power C,W,Power_C,1\n"
    "1,1@1,Power D,W,Power_D,1\n"
    "1,1@1,Power E,W,Power_E,1\n";

static const char *SMI_2_ENERGY =
    "1,1@1,Energy In,Wh,E_in,1\n"
    "1,1@1,Energy Out,Wh,E_out,1\n";

static const char *SMI_3_VOLTAGE =
    "1,1@1,Voltage L1,V,VL1,1\n"
    "1,1@1,Voltage L2,V,VL2,1\n"
    "1,1@1,Voltage L3,V,VL3,1\n";

static const char *TASMOTA_JSON_DEDUP =
    "{\"SML1\":{"
    "\"Power\":1200,"
    "\"OtherPower\":800"
    "}}";

/* Leading whitespace fixtures */

static const char *SMI_LEADING_WS =
    ">D  \n"
    "    >B  \n"
    "    ->sensor53 r\n"
    "    >M 1  \n"
    "    +1,3,s,1,9600,SML  \n"
    "    1,1@1,Bezug Total Wirkarbeit Wh,Wh,Total_Bezug,0\n"
    "    1,1@1,Total Wirkarbeit alle Phasen,W,Total_Wirkleistung,1\n"
    "    1,1@1,Spannung L1,V,Spannung_L1,1\n"
    "    1,1@1,Spannung L2,V,Spannung_L2,1\n"
    "    1,1@1,Spannung L3,V,Spannung_L3,1\n"
    "    1,1@1,Strom L1,A,Strom_L1,1\n"
    "    1,1@1,Strom L2,A,Strom_L2,1\n"
    "    1,1@1,Strom L3,A,Strom_L3,1\n"
    "    1,1@1,Wirkleistung L1,W,Wirkleistung_L1,1\n"
    "    1,1@1,Wirkleistung L2,W,Wirkleistung_L2,1\n"
    "    1,1@1,Wirkleistung L3,W,Wirkleistung_L3,1\n"
    "    1,1@1,Wirkleistung Bezug L1,W,Bezug_L1,1\n"
    "    1,1@1,Wirkleistung Bezug L2,W,Bezug_L2,1\n"
    "    1,1@1,Wirkleistung Bezug L3,W,Bezug_L3,1\n"
    "    1,1@1,Total effect. energy,MWh,E_total,0\n"
    "    1,1@1,Current power,kW,Power_kW,1\n"
    "    1,1@1,Frequency,Hz,Frequency,2\n"
    "    1,1@1,Power factor,,CosPhi,2\n"
    "    1,=h\n"
    "#\n";

static const char *SMI_WITH_GPIO_TRAILING_WS =
    ">D  \n"
    "GPIO3=1\n"
    "GPIO1=3\n"
    "\n"
    "    1,1@1,Strombezug gesamt,Wh,E_total,0\n"
    "    1,1@1,Aktuelle Leistung,W,Power,1\n";

static const char *SMI_WITH_PLUS_LEADING_WS =
    "\n    +1,3,o,16,300,ACE0,1,600,2F3F210D0A  \n"
    "1,1@1,Strombezug gesamt,Wh,E_total,0\n"
    "1,1@1,Aktuelle Leistung,W,Power,1\n";

/* Phase-aware fixture */
static const char *SMI_PHASE_SCRIPT =
    "1,1@1,Verbrauch_Tarif_1,kWh,Verbrauch_T1,7\n"
    "1,1@1,Verbrauch_Tarif_2,kWh,Verbrauch_T2,7\n"
    "1,1@1,Verbrauch_Summe,kWh,Verbrauch_Summe,7\n"
    "1,1@1,Einspeisung_Summe,kWh,Einspeisung_Summe,7\n"
    "1,1@1,Leistung_L1,W,Watt_L1,2\n"
    "1,1@1,Leistung_L2,W,Watt_L2,2\n"
    "1,1@1,Leistung_L3,W,Watt_L3,2\n"
    "1,1@1,Leistung_Summe,W,Watt_Summe,2\n"
    "1,1@1,Spannung_L1,V,Volt_L1,1\n"
    "1,1@1,Spannung_L2,V,Volt_L2,1\n"
    "1,1@1,Spannung_L3,V,Volt_L3,1\n";

/* GPIO fixtures */
static const char *SMI_WITH_GPIO =
    ">D\n"
    "GPIO3=1\n"
    "GPIO1=3\n"
    "\n"
    "1,1@1,Strombezug gesamt,Wh,E_total,0\n"
    "1,1@1,Aktuelle Leistung,W,Power,1\n";

static const char *SMI_WITH_DIFFERENT_GPIO =
    ">D\n"
    "GPIO13=1\n"
    "GPIO15=3\n"
    "\n"
    "1,1@1,Strombezug gesamt,Wh,E_total,0\n";

static const char *SMI_NO_GPIO =
    "1,1@1,Strombezug gesamt,Wh,E_total,0\n";

static const char *SMI_WITH_PLUS_GPIO =
    "+1,3,o,16,300,ACE0,1,600,2F3F210D0A\n"
    "1,1@1,Strombezug gesamt,Wh,E_total,0\n"
    "1,1@1,Aktuelle Leistung,W,Power,1\n";

static const char *SMI_WITH_PLUS_GPIO_ALT =
    "+13,15,o,16,300,ACE0,1,600,2F3F210D0A\n"
    "1,1@1,Strombezug gesamt,Wh,E_total,0\n";
