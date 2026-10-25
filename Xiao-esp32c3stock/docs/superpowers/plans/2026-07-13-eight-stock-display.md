# Eight-Stock Display Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Query eight configured Tencent stock symbols in one HTTP request and display code, price, and colored percentage change in Nextion controls `t0` through `t23`.

**Architecture:** Add a small platform-independent stock parsing module so URL construction and Tencent response parsing can be tested on the host. Keep WiFi, NVS, Web, scheduling, and HMI integration in the Arduino sketch, using fixed-size arrays for predictable ESP32 memory use.

**Tech Stack:** Arduino ESP32, C++11, HTTPClient, Preferences/NVS, Nextion UART, host `g++` tests.

---

### Task 1: Add testable stock batch logic

**Files:**
- Create: `stock_logic.h`
- Create: `stock_logic.cpp`
- Create: `tests/stock_logic_test.cpp`

- [ ] **Step 1: Write failing host tests**

Define tests for strict symbol validation, query-list construction, eight-record parsing, prefix-free display codes, and partial malformed responses. Use this representative input:

```cpp
static const char* CODES[STOCK_COUNT] = {
  "sh000001", "sh000300", "sz399006", "sz399001",
  "sz000660", "sh600460", "sh512760", "sh601162"
};

const char* payload =
  "v_sh000001=\"1~上证指数~000001~3200.10~3190.00~0~0~0~0~0~0~0~0~0~0~0~0~0~0~0~0~0~0~0~0~0~0~0~0~0~0~0~0.32~\";\n"
  "v_sh000300=\"1~沪深300~000300~3800.20~3810.00~0~0~0~0~0~0~0~0~0~0~0~0~0~0~0~0~0~0~0~0~0~0~0~0~0~0~0~-0.26~\";\n";
```

Assertions:

```cpp
assert(isValidStockCode("sh000001"));
assert(isValidStockCode("sz399006"));
assert(!isValidStockCode("000001"));
assert(!isValidStockCode("sh00001"));
assert(buildStockQuery(CODES, query, sizeof(query)));
assert(strcmp(query, "sh000001,sh000300,sz399006,sz399001,sz000660,sh600460,sh512760,sh601162") == 0);
assert(parseTencentBatch(payload, quotes, STOCK_COUNT) == 2);
assert(strcmp(quotes[0].code, "000001") == 0);
assert(strcmp(quotes[0].price, "3200.10") == 0);
assert(strcmp(quotes[0].changePct, "0.32") == 0);
assert(strcmp(quotes[1].changePct, "-0.26") == 0);
```

- [ ] **Step 2: Compile tests and verify RED**

Run:

```powershell
g++ -std=c++11 -Wall -Wextra -pedantic tests/stock_logic_test.cpp stock_logic.cpp -o tests/stock_logic_test.exe
```

Expected: compilation fails because `stock_logic.h` and its functions do not exist yet.

- [ ] **Step 3: Implement the public data model**

`stock_logic.h` exposes fixed-size contracts:

```cpp
#pragma once
#include <stddef.h>

static const size_t STOCK_COUNT = 8;
static const size_t STOCK_CODE_SIZE = 12;

struct StockInfo {
  char code[STOCK_CODE_SIZE];
  char price[16];
  char changePct[12];
  bool valid;
};

bool isValidStockCode(const char* code);
void normalizeStockCode(char* code, size_t len);
bool buildStockQuery(const char codes[][STOCK_CODE_SIZE], char* out, size_t outLen);
size_t parseTencentBatch(const char* payload, StockInfo* quotes, size_t quoteCount);
```

- [ ] **Step 4: Implement minimal parsing logic**

In `stock_logic.cpp`, validate exactly `sh|sz` plus six digits, concatenate all eight symbols with commas while checking capacity, split response records at line/semicolon boundaries, extract the quoted `~`-delimited body, and copy fields 2, 3, and 32 into `code`, `price`, and `changePct`. Only set `valid=true` after all required fields parse.

- [ ] **Step 5: Run tests and verify GREEN**

Run the compile command, then:

```powershell
.\tests\stock_logic_test.exe
```

Expected: exit code 0 and `stock_logic tests passed`.

### Task 2: Replace single-stock state and persistence

**Files:**
- Modify: `xiao_esp32c3_stock.ino`
- Modify: `secrets.h.example`

- [ ] **Step 1: Add eight default symbols**

Replace `STOCK_CODE_DEFAULT` with:

```cpp
#define STOCK_CODES_DEFAULT { \
  "sh000001", "sh000300", "sz399006", "sz399001", \
  "sz000660", "sh600460", "sh512760", "sh601162" \
}
```

Include `stock_logic.h`, remove the old `StockInfo` definition and single `stockCode`/`stock` globals, and add:

```cpp
static const char DEFAULT_STOCK_CODES[STOCK_COUNT][STOCK_CODE_SIZE] = STOCK_CODES_DEFAULT;
char stockCodes[STOCK_COUNT][STOCK_CODE_SIZE] = STOCK_CODES_DEFAULT;
StockInfo stocks[STOCK_COUNT] = {};
```

- [ ] **Step 2: Load eight NVS keys with per-slot defaults**

Implement `loadStockCodes()` using keys `code0` through `code7`. Normalize and validate each loaded value; independently restore the default for an invalid/missing slot.

- [ ] **Step 3: Save all eight values atomically at validation level**

Implement:

```cpp
static bool saveStockCodes(char codes[STOCK_COUNT][STOCK_CODE_SIZE]);
```

Normalize and validate every temporary value before opening writable Preferences. If any value is invalid, write nothing. Otherwise store all `code0`–`code7`, copy to `stockCodes`, and set `lastStockMs = 0`.

- [ ] **Step 4: Re-run host tests**

Run `.\tests\stock_logic_test.exe`.

Expected: all pure stock logic tests still pass.

### Task 3: Expand Web configuration to eight inputs

**Files:**
- Modify: `xiao_esp32c3_stock.ino`

- [ ] **Step 1: Generate eight form controls**

Inside `sendConfigPage`, loop from 0 to 7 and emit `code0` through `code7`, each prefilled from `stockCodes[i]`, `maxlength="8"`, and `required`. Retain the existing success/error redirect behavior.

- [ ] **Step 2: Increase and parse POST capacity**

Increase the POST body buffer from 128 to 256 bytes. For every index, generate the field name with:

```cpp
char key[8];
snprintf(key, sizeof(key), "code%u", (unsigned)i);
extractFormField(body, key, submitted[i], sizeof(submitted[i]));
```

Call `saveStockCodes(submitted)` once after collecting all eight.

- [ ] **Step 3: Verify input boundary behavior**

Review calculations: eight fields contribute at most `8 * (6 key bytes + 8 value bytes + 2 separators) = 128` bytes, so the 256-byte body is sufficient. Confirm malformed or omitted fields cause an error redirect and no NVS writes.

### Task 4: Batch-fetch and display all quotes

**Files:**
- Modify: `xiao_esp32c3_stock.ino`

- [ ] **Step 1: Replace single fetch with batch fetch**

Implement:

```cpp
static bool fetchStocks(StockInfo (&out)[STOCK_COUNT]);
```

Build the comma-separated query with `buildStockQuery`, request `http://qt.gtimg.cn/q=<query>`, parse into a temporary array, and merge only valid slots into `out`. Return true if at least one valid quote was parsed.

- [ ] **Step 2: Map eight quotes to `t0`–`t23`**

Implement `displayStocks()` with base control `i * 3`:

```cpp
int base = (int)i * 3;
hmiSetText(base, stocks[i].code);
hmiSetText(base + 1, stocks[i].price);
hmiSetColor(base + 2, atof(stocks[i].changePct) < 0
                          ? HMI_COLOR_DOWN : HMI_COLOR_UP);
snprintf(pctBuf, sizeof(pctBuf), "%s%%", stocks[i].changePct);
hmiSetText(base + 2, pctBuf);
```

Do not send previous close or clock values in stock mode.

- [ ] **Step 3: Update setup and loop call sites**

Replace `fetchStock(stock)`/`displayStock(stock)` with `fetchStocks(stocks)`/`displayStocks()`. Keep the existing 5-second open-market interval, 10-minute lunch interval, and weekday-only gate unchanged.

- [ ] **Step 4: Update diagnostics and comments**

Change the heartbeat from one stock symbol to `stocks=8`; document the HMI mapping and eight-stock batch behavior in the source header and README.

### Task 5: Final verification

**Files:**
- Verify: `stock_logic.h`
- Verify: `stock_logic.cpp`
- Verify: `tests/stock_logic_test.cpp`
- Verify: `xiao_esp32c3_stock.ino`
- Verify: `secrets.h.example`
- Verify: `README.md`

- [ ] **Step 1: Run host tests with warnings enabled**

```powershell
g++ -std=c++11 -Wall -Wextra -pedantic tests/stock_logic_test.cpp stock_logic.cpp -o tests/stock_logic_test.exe
.\tests\stock_logic_test.exe
```

Expected: compilation has no warnings and tests print `stock_logic tests passed`.

- [ ] **Step 2: Compile the Arduino sketch if Arduino CLI is installed**

```powershell
arduino-cli compile --fqbn Seeeduino:esp32:XIAO_ESP32C3 .
```

Expected: successful compile. If the board package uses a different installed FQBN, obtain it from `arduino-cli board listall` and compile with the matching XIAO ESP32-C3 identifier.

- [ ] **Step 3: Check edited-file diagnostics**

Confirm no new diagnostics in the sketch or stock logic files.

- [ ] **Step 4: Inspect the final diff**

Confirm the diff contains only the eight-stock feature, its tests, source comments, and documentation. Do not commit unless the user explicitly requests it.
