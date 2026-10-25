/*
 * ============================================================================
 *  XIAO ESP32-C3 股票 + 天气信息终端
 * ============================================================================
 *
 * 版本：v2.3.2 (2026-07-13)
 *
 * ── 凭证配置 ───────────────────────────────────────────────
 *   复制 secrets.h.example → secrets.h，填入 WiFi / API Key
 *   secrets.h 不提交 Git；首次克隆后必须自行创建
 *
 * ── 硬件 / 开发环境 ─────────────────────────────────────────
 *   板型：Seeed Studio XIAO ESP32C3
 *   IDE ：Arduino → 开发板 XIAO_ESP32C3
 *         USB CDC On Boot = Enabled
 *         USB Mode        = Hardware CDC and JTAG
 *         串口监视器       = 115200
 *
 * ── 功能概览 ────────────────────────────────────────────────
 *   · A 股行情   腾讯 qt.gtimg.cn（一次批量查询 8 只）
 *   · 天气       OpenWeatherMap（默认深圳）
 *   · 时钟       NTP 北京时间 UTC+8
 *   · 显示逻辑   仅工作日刷新股票
 *               交易日 9:30-11:30 / 13:00-15:00 → 股票（3s 刷新）
 *               午休 11:30-13:00 → 股票（10min 刷新）
 *               非工作日及收盘后 → 时间 + 天气（不拉股票）
 *   · Nextion HMI  Serial1，115200
 *   · OLED 可选    SSD1306 I2C（OLED_ENABLE=1）
 *   · Web 配置     http://<设备IP>/  修改 8 个股票代码，NVS 持久化
 *
 * ── Web 配置页 ─────────────────────────────────────────────
 *   1. 设备与手机/电脑连接同一 WiFi
 *   2. 串口查看 IP，浏览器打开 http://192.168.x.x/
 *   3. 输入 8 个代码保存，格式：sh600460（沪）/ sz000001（深）
 *   4. 重启后仍有效；交易时段内保存后立即刷新行情
 *
 * ── HMI 控件（Nextion t 文本）──────────────────────────────
 *   非交易：t0时间 t1星期 t2日期 t3城市 t4天气 t5温度 t6湿度 t7气压 t8风速
 *   交易：  每只占 3 个控件：代码/价格/涨跌幅(红涨绿跌)
 *            股票1=t0/t1/t2，股票2=t3/t4/t5，…，股票8=t21/t22/t23
 *
 * ── HMI 串口接线（HMI_PIN_MODE，默认 1）────────────────────
 *   模式 0 — D10(TX)→Nextion RX，D9(RX)←Nextion TX  （改线，最稳）
 *   模式 1 — D6(TX)→Nextion RX，D7(RX)←Nextion TX   （旧线，方案A）
 *            USB 调试与 HMI 并行：先 Serial(USB)，延时 3s 后 Serial1
 *
 * ── 引脚速查 ───────────────────────────────────────────────
 *   D4/D5=I2C  D6/D7=HMI模式1  D8=LED  D9/D10=HMI模式0
 *   Serial=USB CDC 调试（115200）
 *
 * ── 主要编译宏 ─────────────────────────────────────────────
 *   OLED_ENABLE=0/1   DEBUG_LOG=0/1   STOCK_RAW_LOG=0/1
 *   HMI_PIN_MODE=0/1
 *
 * ── 更新记录 ───────────────────────────────────────────────
 *   v2.3.2  2026-07-13  交易刷新改为 3s；行情原文日志独立开关
 *   v2.3.1  2026-07-13  取消行情记录 512 字节限制
 *   v2.3.0  2026-07-13  8 只股票批量查询、显示和 Web 配置
 *   v2.2.5  2026-07-07  凭证分离至 secrets.h（不入库）
 *   v2.2.4  2026-07-07  整理程序头说明；Web 仅用 IP 访问
 *   v2.2.3  2026-07-07  移除 mDNS stockconfig.local
 *   v2.2.0  2026-07-07  Web 配置页 + NVS 保存股票代码
 *   v2.1.0  2026-07-07  方案 A：D6/D7 HMI 与 USB 调试并存
 *   v2.0.x  2026-07-07  重构：交易时段、WiFi 重连、HMI 封装
 *   v1.x    2026-02~03  初版：ESP8266/XIAO，股票+天气+OLED/HMI
 * ============================================================================
 */

// ── 固件版本 ──────────────────────────────────────────────
#define FW_VERSION_MAJOR  2
#define FW_VERSION_MINOR  3
#define FW_VERSION_PATCH  2
#define FW_BUILD_DATE     "2026-07-13"
#define FW_VERSION        "v2.3.2 (" FW_BUILD_DATE ")"

// ── 编译开关 ──────────────────────────────────────────────
#define OLED_ENABLE       0   // 1=启用 SSD1306
#define DEBUG_LOG         1   // 1=串口调试输出
#define STOCK_RAW_LOG     0   // 1=打印腾讯接口完整原始响应

// ── HMI 串口引脚（详见文件头）────────────────────────────
// 0 = D10/D9  UART1  改线方案
// 1 = D6/D7   UART1  方案 A：旧接线 + USB 调试（已验证 2026-07-07）
#define HMI_PIN_MODE      1
#if HMI_PIN_MODE == 1
  #define HMI_INIT_DELAY_MS 3000   // D6/D7 模式：等 USB 枚举 + Bootloader 结束后再开 HMI
#endif

// ── 刷新间隔（毫秒） ──────────────────────────────────────
static const unsigned long STOCK_INTERVAL_MS       = 3000;    // 交易时段股票 3s
static const unsigned long LUNCH_STOCK_INTERVAL_MS = 600000;  // 午休股票 10min
static const unsigned long DISPLAY_INTERVAL_MS     = 10000;   // 时间/天气界面 10s
static const unsigned long WEATHER_INTERVAL_MS = 1800000; // 天气 30min
static const unsigned long NTP_INTERVAL_MS     = 3600000; // NTP 校准 1h
static const unsigned long WIFI_RETRY_MS       = 30000;   // WiFi 重试间隔

#include "secrets.h"   // WiFi / API Key，见 secrets.h.example
#include "stock_logic.h"

// ── HMI 颜色（A 股：红涨绿跌） ───────────────────────────
static const uint16_t HMI_COLOR_UP   = 63488;  // 红
static const uint16_t HMI_COLOR_DOWN = 2016;   // 绿
static const uint16_t HMI_COLOR_NEUTRAL = 65535; // 白

// ── 库 ────────────────────────────────────────────────────
#include <Wire.h>
#if OLED_ENABLE
#include <Adafruit_GFX.h>
#include <Adafruit_SSD1306.h>
#define OLED_SDA SDA
#define OLED_SCL SCL
#endif

#include <WiFi.h>
#include <Preferences.h>
#include <HTTPClient.h>
#include <WiFiClient.h>
#include <NTPClient.h>
#include <WiFiUdp.h>
#include <ArduinoJson.h>
#include <cstring>
#include <esp_system.h>
#include <esp_log.h>

#ifndef LED_BUILTIN
#define LED_BUILTIN 8   // XIAO ESP32C3 用户 LED
#endif

#if DEBUG_LOG
  #define LOG(...) Serial.printf(__VA_ARGS__)
  #define LOGLN(x) Serial.println(x)
#else
  #define LOG(...)
  #define LOGLN(x)
#endif

// ── 数据结构 ──────────────────────────────────────────────
struct WeatherInfo {
  char city[32];
  char description[32];
  float temperature;
  float humidity;
  float pressure;
  float windSpeed;
  bool valid;
};

struct ClockInfo {
  int year, month, day;
  int hour, minute, second;
  int weekday;       // 0=Sunday … 6=Saturday
  bool isWeekday;
  bool isMarketOpen;
  bool isMarketLunch;   // 工作日 11:30-13:00 午休
};

// ── 全局状态 ──────────────────────────────────────────────
WiFiUDP ntpUDP;
NTPClient timeClient(ntpUDP, "pool.ntp.org", 8 * 3600, NTP_INTERVAL_MS);

#if OLED_ENABLE
Adafruit_SSD1306 display(128, 64, &Wire, -1);
#endif

static const char DEFAULT_STOCK_CODES[STOCK_COUNT][STOCK_CODE_SIZE] = {
  "sh000001", "sh000300", "sz399006", "sz399001",
  "sz000660", "sh600460", "sh512760", "sh601162"
};

char stockCodes[STOCK_COUNT][STOCK_CODE_SIZE] = {};
StockInfo stocks[STOCK_COUNT] = {};
WeatherInfo weather = {};
ClockInfo  localTime = {};

Preferences prefs;
WiFiServer configServer(80);

static const char* PREFS_NS = "stockcfg";

time_t epochAtSync = 0;
unsigned long lastTimeSyncMs = 0;
unsigned long lastStockMs    = 0;
unsigned long lastDisplayMs  = 0;
unsigned long lastWeatherMs  = 0;
unsigned long lastNtpMs       = 0;
unsigned long lastWifiRetryMs = 0;
unsigned long lastHeartbeatMs = 0;

// ── HMI 通信 ──────────────────────────────────────────────
static void hmiSendRaw(const char* cmd) {
  Serial1.print(cmd);
  Serial1.write(0xFF);
  Serial1.write(0xFF);
  Serial1.write(0xFF);
}

static void hmiSetText(int id, const char* text) {
  char buf[96];
  snprintf(buf, sizeof(buf), "t%d.txt=\"%s\"", id, text);
  hmiSendRaw(buf);
}

static void hmiSetColor(int id, uint16_t color) {
  char buf[32];
  snprintf(buf, sizeof(buf), "t%d.pco=%u", id, color);
  hmiSendRaw(buf);
}

// ── 时间 ──────────────────────────────────────────────────
static bool syncNtpTime() {
  if (!timeClient.update()) {
    return epochAtSync > 0;
  }
  epochAtSync = timeClient.getEpochTime();
  lastTimeSyncMs = millis();
  LOGLN("NTP synced");
  return epochAtSync > 0;
}

static void updateClock() {
  if (epochAtSync == 0) return;

  time_t epoch = epochAtSync + (millis() - lastTimeSyncMs) / 1000;
  struct tm* t = gmtime(&epoch);
  if (!t) return;

  localTime.year    = t->tm_year + 1900;
  localTime.month   = t->tm_mon + 1;
  localTime.day     = t->tm_mday;
  localTime.hour    = t->tm_hour;
  localTime.minute  = t->tm_min;
  localTime.second  = t->tm_sec;
  localTime.weekday = t->tm_wday;
  localTime.isWeekday = (localTime.weekday >= 1 && localTime.weekday <= 5);

  int minutes = localTime.hour * 60 + localTime.minute;
  bool morning = (minutes >= 9 * 60 + 30 && minutes < 11 * 60 + 30);
  bool lunch = (minutes >= 11 * 60 + 30 && minutes < 13 * 60);
  bool afternoon = (minutes >= 13 * 60 && minutes < 15 * 60);
  localTime.isMarketOpen = localTime.isWeekday && (morning || afternoon);
  localTime.isMarketLunch = localTime.isWeekday && lunch;

#if DEBUG_LOG
  static int lastLogSecond = -1;
  static bool lastMarketOpen = false;
  static bool lastMarketLunch = false;
  if (localTime.second != lastLogSecond
      || localTime.isMarketOpen != lastMarketOpen
      || localTime.isMarketLunch != lastMarketLunch) {
    lastLogSecond = localTime.second;
    lastMarketOpen = localTime.isMarketOpen;
    lastMarketLunch = localTime.isMarketLunch;
    const char* phase = !localTime.isWeekday ? "weekend"
                      : localTime.isMarketOpen ? "open"
                      : localTime.isMarketLunch ? "lunch"
                      : "closed";
    LOG("Time: %04d-%02d-%02d %02d:%02d:%02d  market=%s\n",
        localTime.year, localTime.month, localTime.day,
        localTime.hour, localTime.minute, localTime.second, phase);
  }
#endif
}

static bool shouldRefreshStock() {
  return localTime.isWeekday && (localTime.isMarketOpen || localTime.isMarketLunch);
}

static unsigned long stockRefreshIntervalMs() {
  if (!localTime.isWeekday) return 0;
  if (localTime.isMarketOpen) return STOCK_INTERVAL_MS;
  if (localTime.isMarketLunch) return LUNCH_STOCK_INTERVAL_MS;
  return 0;
}

static void printWeekdayHmi(int weekday) {
  static const char* DAYS[] = {
    "Sunday", "Monday", "Tuesday", "Wednesday",
    "Thursday", "Friday", "Saturday"
  };
  if (weekday >= 0 && weekday <= 6) {
    hmiSetText(1, DAYS[weekday]);
  }
}

// ── WiFi ──────────────────────────────────────────────────
static bool ensureWiFi() {
  if (WiFi.status() == WL_CONNECTED) return true;

  unsigned long now = millis();
  if (now - lastWifiRetryMs < WIFI_RETRY_MS) return false;
  lastWifiRetryMs = now;

  LOGLN("WiFi disconnected, reconnecting...");
  WiFi.disconnect();
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);

  unsigned long start = millis();
  while (WiFi.status() != WL_CONNECTED && millis() - start < 15000) {
    delay(500);
  }

  if (WiFi.status() == WL_CONNECTED) {
    LOG("WiFi OK, IP: %s\n", WiFi.localIP().toString().c_str());
    LOG("Web config: http://%s/\n", WiFi.localIP().toString().c_str());
    return true;
  }
  LOGLN("WiFi reconnect failed");
  return false;
}

static void connectWiFiBlocking() {
  LOGLN("Connecting to WiFi...");
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);

  unsigned long start = millis();
  int attempt = 0;
  while (WiFi.status() != WL_CONNECTED) {
    delay(1000);
    attempt++;
    LOG("  WiFi waiting... %ds (status=%d)\n", attempt, WiFi.status());
    if (attempt >= 60) {
      LOGLN("WiFi connect timeout (60s), check SSID/password");
      return;
    }
  }
  LOG("Connected, IP: %s\n", WiFi.localIP().toString().c_str());
  LOG("Web config: http://%s/\n", WiFi.localIP().toString().c_str());
}

// ── 股票代码配置（NVS + Web）──────────────────────────────
static void loadStockCodes() {
  prefs.begin(PREFS_NS, true);
  for (size_t i = 0; i < STOCK_COUNT; ++i) {
    char key[8];
    snprintf(key, sizeof(key), "code%u", (unsigned)i);
    String saved = prefs.getString(key, DEFAULT_STOCK_CODES[i]);
    strlcpy(stockCodes[i], saved.c_str(), sizeof(stockCodes[i]));
    normalizeStockCode(stockCodes[i], sizeof(stockCodes[i]));
    if (!isValidStockCode(stockCodes[i])) {
      strlcpy(stockCodes[i], DEFAULT_STOCK_CODES[i], sizeof(stockCodes[i]));
    }
    strlcpy(stocks[i].code, stockCodes[i] + 2, sizeof(stocks[i].code));
    LOG("Stock %u code: %s\n", (unsigned)(i + 1), stockCodes[i]);
  }
  prefs.end();
}

static bool saveStockCodes(char codes[STOCK_COUNT][STOCK_CODE_SIZE]) {
  for (size_t i = 0; i < STOCK_COUNT; ++i) {
    normalizeStockCode(codes[i], STOCK_CODE_SIZE);
    if (!isValidStockCode(codes[i])) return false;
  }

  if (!prefs.begin(PREFS_NS, false)) {
    LOGLN("NVS open failed");
    return false;
  }

  bool writeOk = true;
  for (size_t i = 0; i < STOCK_COUNT; ++i) {
    char key[8];
    snprintf(key, sizeof(key), "code%u", (unsigned)i);
    if (prefs.putString(key, codes[i]) != strlen(codes[i])) {
      writeOk = false;
      break;
    }
  }

  if (!writeOk) {
    // 尽力恢复原配置；运行时状态只在全部写入成功后更新。
    for (size_t i = 0; i < STOCK_COUNT; ++i) {
      char key[8];
      snprintf(key, sizeof(key), "code%u", (unsigned)i);
      prefs.putString(key, stockCodes[i]);
    }
    prefs.end();
    LOGLN("NVS stock code write failed");
    return false;
  }

  for (size_t i = 0; i < STOCK_COUNT; ++i) {
    bool changed = strcmp(stockCodes[i], codes[i]) != 0;
    strlcpy(stockCodes[i], codes[i], sizeof(stockCodes[i]));
    if (changed) {
      stocks[i] = {};
      strlcpy(stocks[i].code, stockCodes[i] + 2, sizeof(stocks[i].code));
    }
  }
  prefs.end();
  // 用最长刷新周期回拨，确保交易或午休时保存后下一轮立即查询。
  lastStockMs = millis() - LUNCH_STOCK_INTERVAL_MS;
  LOGLN("All 8 stock codes saved");
  return true;
}

static void extractFormField(const char* body, const char* key, char* out, size_t outLen) {
  char pattern[16];
  snprintf(pattern, sizeof(pattern), "%s=", key);
  const char* p = strstr(body, pattern);
  if (!p) {
    out[0] = '\0';
    return;
  }
  p += strlen(pattern);
  size_t i = 0;
  while (*p && *p != '&' && i + 1 < outLen) {
    out[i++] = (*p == '+') ? ' ' : *p;
    p++;
  }
  out[i] = '\0';
}

static void httpSendRedirect(WiFiClient& client, const char* location) {
  client.println("HTTP/1.1 303 See Other");
  client.print("Location: ");
  client.println(location);
  client.println("Connection: close");
  client.println();
}

static void httpSendHtml(WiFiClient& client, const String& html) {
  client.println("HTTP/1.1 200 OK");
  client.println("Content-Type: text/html; charset=utf-8");
  client.println("Connection: close");
  client.println();
  client.print(html);
}

static void sendConfigPage(WiFiClient& client, bool saved, bool error) {
  String html = R"rawhtml(<!DOCTYPE html>
<html lang="zh-CN"><head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>股票终端配置</title>
<style>
*{box-sizing:border-box}body{font-family:sans-serif;max-width:420px;margin:24px auto;padding:0 16px;background:#f5f5f5}
.card{background:#fff;border-radius:8px;padding:20px;box-shadow:0 1px 4px rgba(0,0,0,.1)}
h1{font-size:1.25rem;margin:0 0 8px}p{color:#666;font-size:.9rem;margin:0 0 16px}
label{display:block;margin-bottom:6px;font-weight:600}
input{width:100%;padding:10px;font-size:1rem;border:1px solid #ccc;border-radius:6px}
button{margin-top:16px;width:100%;padding:12px;font-size:1rem;background:#1976d2;color:#fff;border:0;border-radius:6px;cursor:pointer}
.ok{color:#2e7d32;background:#e8f5e9;padding:10px;border-radius:6px;margin-bottom:12px}
.err{color:#c62828;background:#ffebee;padding:10px;border-radius:6px;margin-bottom:12px}
.stock-field{margin-top:12px}.info{font-size:.85rem;color:#888;margin-top:16px;line-height:1.5}
</style></head><body>
<div class="card">
<h1>股票代码配置</h1>
<p>)rawhtml";
  html += FW_VERSION;
  html += " · IP ";
  html += WiFi.localIP().toString();
  html += "</p>";

  if (saved) {
    html += R"rawhtml(<div class="ok">已保存，下次刷新股票时生效</div>)rawhtml";
  }
  if (error) {
    html += R"rawhtml(<div class="err">格式错误：每项必须为 sh/sz 加 6 位数字</div>)rawhtml";
  }

  html += R"rawhtml(
<form method="POST" action="/save">)rawhtml";
  for (size_t i = 0; i < STOCK_COUNT; ++i) {
    html += R"rawhtml(<div class="stock-field"><label for="code)rawhtml";
    html += i;
    html += R"rawhtml(">股票 )rawhtml";
    html += i + 1;
    html += R"rawhtml(</label><input id="code)rawhtml";
    html += i;
    html += R"rawhtml(" name="code)rawhtml";
    html += i;
    html += R"rawhtml(" value=")rawhtml";
    html += stockCodes[i];
    html += R"rawhtml(" placeholder="sh000001" maxlength="8" required></div>)rawhtml";
  }
  html += R"rawhtml(
<button type="submit">保存</button>
</form>
<div class="info">
格式：sh + 6位数字（上海）或 sz + 6位数字（深圳）<br>
8 个代码全部验证通过后统一保存
</div></div></body></html>)rawhtml";

  httpSendHtml(client, html);
}

static void handleConfigClient(WiFiClient client) {
  client.setTimeout(2000);
  String reqLine = client.readStringUntil('\n');
  if (reqLine.length() == 0) {
    client.stop();
    return;
  }

  char method[8] = {};
  char path[128] = {};
  sscanf(reqLine.c_str(), "%7s %127s", method, path);

  int contentLength = 0;
  while (client.connected()) {
    String header = client.readStringUntil('\n');
    header.trim();
    if (header.length() == 0) break;
    if (header.startsWith("Content-Length:")) {
      contentLength = header.substring(15).toInt();
    }
  }

  if (strcmp(method, "POST") == 0 && strstr(path, "/save") != nullptr) {
    char body[256] = {};
    if (contentLength > 0) {
      int toRead = contentLength;
      if (toRead >= (int)sizeof(body)) toRead = (int)sizeof(body) - 1;
      client.readBytes(body, toRead);
    }
    char submitted[STOCK_COUNT][STOCK_CODE_SIZE] = {};
    for (size_t i = 0; i < STOCK_COUNT; ++i) {
      char key[8];
      snprintf(key, sizeof(key), "code%u", (unsigned)i);
      extractFormField(body, key, submitted[i], sizeof(submitted[i]));
    }
    if (saveStockCodes(submitted)) {
      httpSendRedirect(client, "/?saved=1");
    } else {
      httpSendRedirect(client, "/?error=1");
    }
    client.stop();
    return;
  }

  bool saved = strstr(path, "saved=1") != nullptr;
  bool errFlag = strstr(path, "error=1") != nullptr;
  sendConfigPage(client, saved, errFlag);
  client.stop();
}

static void pollConfigServer() {
  WiFiClient client = configServer.available();
  if (client) {
    handleConfigClient(client);
  }
}

static void setupWebServer() {
  configServer.begin();
  LOGLN("Web server started on port 80 (WiFiServer)");
}

// ── HTTP 工具 ─────────────────────────────────────────────
static void configureHttp(HTTPClient& http) {
  http.setConnectTimeout(5000);
  http.setTimeout(10000);
}

// ── 天气 ──────────────────────────────────────────────────
static bool fetchWeather() {
  char url[256];
  snprintf(url, sizeof(url),
           "http://api.openweathermap.org/data/2.5/weather?q=%s,%s&appid=%s&units=metric",
           WEATHER_CITY, WEATHER_COUNTRY, WEATHER_API_KEY);

  HTTPClient http;
  configureHttp(http);
  http.begin(url);

  int code = http.GET();
  if (code != HTTP_CODE_OK) {
    LOG("Weather HTTP error: %d\n", code);
    http.end();
    return false;
  }

  DynamicJsonDocument doc(1536);
  DeserializationError err = deserializeJson(doc, http.getStream());
  http.end();

  if (err) {
    LOG("Weather JSON error: %s\n", err.c_str());
    return false;
  }

  strlcpy(weather.city, doc["name"] | "", sizeof(weather.city));
  strlcpy(weather.description, doc["weather"][0]["main"] | "", sizeof(weather.description));
  weather.temperature = doc["main"]["temp"] | 0.0f;
  weather.humidity    = doc["main"]["humidity"] | 0.0f;
  weather.pressure    = doc["main"]["pressure"] | 0.0f;
  weather.windSpeed   = doc["wind"]["speed"] | 0.0f;
  weather.valid       = true;

  LOG("Weather: %s %s %.1fC\n", weather.city, weather.description, weather.temperature);
  return true;
}

// ── 股票批量查询 ──────────────────────────────────────────
static bool fetchStocks(StockInfo (&out)[STOCK_COUNT]) {
  char query[96];
  if (!buildStockQuery(stockCodes, query, sizeof(query))) {
    LOGLN("Stock query build failed");
    return false;
  }

  char url[128];
  snprintf(url, sizeof(url), "http://qt.gtimg.cn/q=%s", query);

  HTTPClient http;
  WiFiClient client;
  configureHttp(http);
  http.begin(client, url);

  int code = http.GET();
  if (code != HTTP_CODE_OK) {
    LOG("Stock HTTP error: %d\n", code);
    http.end();
    return false;
  }

  String payload = http.getString();
  http.end();
#if STOCK_RAW_LOG
  LOGLN(payload);
#endif

  StockInfo fresh[STOCK_COUNT] = {};
  size_t parsed = parseTencentBatch(payload.c_str(), stockCodes,
                                    fresh, STOCK_COUNT);
  mergeStockQuotes(out, fresh, STOCK_COUNT);
  LOG("Stock batch parsed: %u/%u\n", (unsigned)parsed, (unsigned)STOCK_COUNT);
  return parsed > 0;
}

// ── 显示：股票 ────────────────────────────────────────────
#if OLED_ENABLE
static void oledShowWelcome() {
  display.clearDisplay();
  display.setTextSize(2);
  display.setTextColor(WHITE);
  display.setCursor(0, 0);
  display.print("welcome STOCK");
  display.display();
  delay(500);
  display.clearDisplay();
}

static void oledShowStocks() {
  display.clearDisplay();
  display.setTextColor(WHITE);
  display.setTextSize(1);
  for (size_t i = 0; i < 4; ++i) {
    display.setCursor(0, (int)i * 14);
    display.printf("%s %s %s%%", stocks[i].code,
                   stocks[i].valid ? stocks[i].price : "--",
                   stocks[i].valid ? stocks[i].changePct : "--");
  }
  display.display();
}

static void oledShowTimeWeather() {
  char timeStr[8], dayStr[12];
  snprintf(timeStr, sizeof(timeStr), "%02d:%02d", localTime.hour, localTime.minute);
  snprintf(dayStr, sizeof(dayStr), "%04d-%02d-%02d", localTime.year, localTime.month, localTime.day);

  display.clearDisplay();
  display.setTextColor(WHITE);
  display.setTextSize(1);
  display.setCursor(0, 0);
  display.printf("%s  wk:%d", dayStr, localTime.weekday);
  display.setTextSize(2);
  display.setCursor(15, 16);
  display.print(timeStr);
  display.setTextSize(1);
  display.setCursor(0, 35);
  display.printf("City:%s %s", weather.city, weather.description);
  display.setCursor(0, 45);
  display.printf("T:%.0fC  H:%.0f%%", weather.temperature, weather.humidity);
  display.setCursor(0, 55);
  display.printf("%.0f hPa  %.1f m/s", weather.pressure, weather.windSpeed);
  display.display();
}

static void oledShowError(const char* msg) {
  display.clearDisplay();
  display.setTextSize(1);
  display.setCursor(0, 0);
  display.print(msg);
  display.display();
}

static void i2cScanner() {
  LOGLN("I2C scanning...");
  int found = 0;
  for (byte addr = 1; addr < 127; addr++) {
    Wire.beginTransmission(addr);
    if (Wire.endTransmission() == 0) {
      LOG("  device 0x%02X\n", addr);
      found++;
    }
  }
  LOG("I2C scan done, %d device(s)\n", found);
}
#endif

static void displayStocks() {
  for (size_t i = 0; i < STOCK_COUNT; ++i) {
    int base = (int)i * 3;
    hmiSetText(base, stocks[i].code);
    hmiSetText(base + 1, stocks[i].valid ? stocks[i].price : "--");

    char pctBuf[16];
    if (stocks[i].valid) {
      float change = atof(stocks[i].changePct);
      hmiSetColor(base + 2, change < 0 ? HMI_COLOR_DOWN : HMI_COLOR_UP);
      snprintf(pctBuf, sizeof(pctBuf), "%s%%", stocks[i].changePct);
    } else {
      hmiSetColor(base + 2, HMI_COLOR_NEUTRAL);
      strlcpy(pctBuf, "--", sizeof(pctBuf));
    }
    hmiSetText(base + 2, pctBuf);
  }

#if OLED_ENABLE
  oledShowStocks();
#endif
}

static void displayTimeWeather() {
  char timeStr[8], dayStr[12];
  char buf[24];

  snprintf(timeStr, sizeof(timeStr), "%02d:%02d", localTime.hour, localTime.minute);
  snprintf(dayStr, sizeof(dayStr), "%04d-%02d-%02d", localTime.year, localTime.month, localTime.day);

  hmiSetText(0, timeStr);
  hmiSetText(2, dayStr);
  printWeekdayHmi(localTime.weekday);

  if (weather.valid) {
    hmiSetText(3, weather.city);
    hmiSetText(4, weather.description);
    snprintf(buf, sizeof(buf), "%.0fC", weather.temperature);
    hmiSetText(5, buf);
    snprintf(buf, sizeof(buf), "%.0f%%", weather.humidity);
    hmiSetText(6, buf);
    snprintf(buf, sizeof(buf), "%.0fhPa", weather.pressure);
    hmiSetText(7, buf);
    snprintf(buf, sizeof(buf), "%.1f m/s", weather.windSpeed);
    hmiSetText(8, buf);
  }

#if OLED_ENABLE
  oledShowTimeWeather();
#endif
}

// ── setup / loop ──────────────────────────────────────────
static const char* resetReasonStr(esp_reset_reason_t reason) {
  switch (reason) {
    case ESP_RST_POWERON:  return "POWERON";
    case ESP_RST_SW:       return "SW_RESET";
    case ESP_RST_PANIC:    return "PANIC";
    case ESP_RST_INT_WDT:  return "INT_WDT";
    case ESP_RST_TASK_WDT: return "TASK_WDT";
    case ESP_RST_WDT:      return "WDT";
    case ESP_RST_BROWNOUT: return "BROWNOUT";
    default:               return "OTHER";
  }
}

static void blinkLed(int times, int msOn = 150) {
  pinMode(LED_BUILTIN, OUTPUT);
  digitalWrite(LED_BUILTIN, HIGH);
  for (int i = 0; i < times; i++) {
    digitalWrite(LED_BUILTIN, LOW);
    delay(msOn);
    digitalWrite(LED_BUILTIN, HIGH);
    delay(msOn);
  }
}

static void initUsbSerial() {
  // CDC On Boot 已由框架初始化，勿再调用 USB.begin()
  Serial.begin(115200);
  delay(2000);  // 等 Windows 重新枚举 COM 口

  esp_reset_reason_t rr = esp_reset_reason();
  Serial.printf("\n\n[BOOT] %s  reset=%s\n", FW_VERSION, resetReasonStr(rr));
#if ARDUINO_USB_CDC_ON_BOOT
  Serial.println("[BOOT] USB CDC: ENABLED  (Tools -> USB Mode -> Hardware CDC and JTAG)");
#else
  Serial.println("[BOOT] USB CDC: DISABLED");
#endif
  Serial.flush();
}

static void initHmiSerial() {
#if HMI_PIN_MODE == 1
  delay(HMI_INIT_DELAY_MS);
  // UART1 映射到 D6/D7；Serial 仍走 USB CDC，二者硬件独立
  Serial1.begin(115200, SERIAL_8N1, D7, D6);
  LOGLN("HMI UART1 on D6/D7 (USB debug compatible, delayed init)");
#else
  Serial1.begin(115200, SERIAL_8N1, D9, D10);
  LOGLN("HMI UART1 on D9(RX)/D10(TX)");
#endif
  // 可选：向 Nextion 发复位指令清掉 Bootloader 乱码（取消注释启用）
  // Serial1.print("rest");
  // Serial1.write(0xFF); Serial1.write(0xFF); Serial1.write(0xFF);
}

void setup() {
  initUsbSerial();
  blinkLed(2);
  LOGLN("=== XIAO ESP32-C3 Stock + Weather ===");

  initHmiSerial();
  Serial1.print("HMI UART ready");

#if OLED_ENABLE
  Wire.begin(OLED_SDA, OLED_SCL);
  display.begin(SSD1306_SWITCHCAPVCC, 0x3C);
  display.clearDisplay();
  i2cScanner();
  oledShowWelcome();
  oledShowError("Connecting WiFi...");
#endif

  connectWiFiBlocking();

  loadStockCodes();
  setupWebServer();

  timeClient.begin();
  LOGLN("Syncing NTP...");
  while (!syncNtpTime()) {
    delay(1000);
  }
  lastNtpMs = millis();

  fetchWeather();
  lastWeatherMs = millis();
  updateClock();

  // 启动后立即刷新一次界面
  if (shouldRefreshStock()) {
    fetchStocks(stocks);
    displayStocks();
  } else {
    displayTimeWeather();
  }
  lastStockMs = lastDisplayMs = millis();
}

void loop() {
  unsigned long now = millis();

  // 定期 NTP 校准
  if (now - lastNtpMs >= NTP_INTERVAL_MS) {
    syncNtpTime();
    lastNtpMs = now;
  }
  updateClock();

  if (!ensureWiFi()) {
    delay(1000);
    return;
  }

  pollConfigServer();

  // 定期刷新天气
  if (now - lastWeatherMs >= WEATHER_INTERVAL_MS) {
    fetchWeather();
    lastWeatherMs = now;
  }

  bool stockMode = shouldRefreshStock();
  static bool wasStockMode = false;
  if (wasStockMode && !stockMode) {
    displayTimeWeather();
    lastDisplayMs = now;
  }
  wasStockMode = stockMode;

  unsigned long stockInterval = stockRefreshIntervalMs();
  if (stockInterval > 0) {
    if (now - lastStockMs >= stockInterval) {
      if (fetchStocks(stocks)) displayStocks();
      lastStockMs = now;
    }
  } else {
    if (now - lastDisplayMs >= DISPLAY_INTERVAL_MS) {
      displayTimeWeather();
      lastDisplayMs = now;
    }
  }

  delay(50);

  // 每 30s 心跳，确认程序在运行
  if (now - lastHeartbeatMs >= 30000) {
    const char* phase = !localTime.isWeekday ? "weekend"
                      : localTime.isMarketOpen ? "open"
                      : localTime.isMarketLunch ? "lunch"
                      : "closed";
    LOG("[HB] uptime=%lus  wifi=%d  market=%s  stocks=%u\n",
        now / 1000, WiFi.status(), phase, (unsigned)STOCK_COUNT);
    lastHeartbeatMs = now;
  }
}
