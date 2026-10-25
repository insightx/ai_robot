#include "../stock_logic.h"

#include <cassert>
#include <cstring>
#include <iostream>
#include <string>

static const char CODES[STOCK_COUNT][STOCK_CODE_SIZE] = {
  "sh000001", "sh000300", "sz399006", "sz399001",
  "sz000660", "sh600460", "sh512760", "sh601162"
};

static std::string makeRecord(const char* marketCode,
                              const char* displayCode,
                              const char* price,
                              const char* changePct) {
  std::string record = "v_";
  record += marketCode;
  record += "=\"1~name~";
  record += displayCode;
  record += "~";
  record += price;
  for (int field = 4; field < 32; ++field) {
    record += "~0";
  }
  record += "~";
  record += changePct;
  record += "~\";\n";
  return record;
}

static void testStockCodeValidationAndNormalization() {
  assert(isValidStockCode("sh000001"));
  assert(isValidStockCode("sz399006"));
  assert(!isValidStockCode("000001"));
  assert(!isValidStockCode("sh00001"));
  assert(!isValidStockCode("xx000001"));
  assert(!isValidStockCode("sh00000a"));

  char code[] = "SH600460";
  normalizeStockCode(code, sizeof(code));
  assert(std::strcmp(code, "sh600460") == 0);
}

static void testBatchQueryConstruction() {
  char query[96] = {};
  assert(buildStockQuery(CODES, query, sizeof(query)));
  assert(std::strcmp(
    query,
    "sh000001,sh000300,sz399006,sz399001,sz000660,sh600460,sh512760,sh601162"
  ) == 0);

  char tooSmall[16] = {};
  assert(!buildStockQuery(CODES, tooSmall, sizeof(tooSmall)));
}

static void testAllEightRecordsMapByCodeWhenReordered() {
  const char* displayCodes[STOCK_COUNT] = {
    "000001", "000300", "399006", "399001",
    "000660", "600460", "512760", "601162"
  };
  const char* prices[STOCK_COUNT] = {
    "1.01", "2.02", "3.03", "4.04", "5.05", "6.06", "7.07", "8.08"
  };

  std::string payload;
  for (int i = (int)STOCK_COUNT - 1; i >= 0; --i) {
    payload += makeRecord(CODES[i], displayCodes[i], prices[i], "0.10");
  }

  StockInfo quotes[STOCK_COUNT] = {};
  size_t parsed = parseTencentBatch(payload.c_str(), CODES,
                                    quotes, STOCK_COUNT);

  assert(parsed == STOCK_COUNT);
  for (size_t i = 0; i < STOCK_COUNT; ++i) {
    assert(quotes[i].valid);
    assert(std::strcmp(quotes[i].code, displayCodes[i]) == 0);
    assert(std::strcmp(quotes[i].price, prices[i]) == 0);
  }
}

static void testMalformedMissingDuplicateAndUnknownRecordsAreIsolated() {
  std::string payload = makeRecord("sh000001", "000001", "3200.10", "0.32");
  payload += "v_sz399006=\"not-a-valid-record\";\n";
  payload += makeRecord("sh000300", "000300", "3800.20", "-0.26");
  payload += makeRecord("sh000001", "000001", "9999.99", "9.99");
  payload += makeRecord("sh999999", "999999", "1.00", "1.00");

  StockInfo quotes[STOCK_COUNT] = {};
  size_t parsed = parseTencentBatch(payload.c_str(), CODES,
                                    quotes, STOCK_COUNT);

  assert(parsed == 2);
  assert(quotes[0].valid);
  assert(std::strcmp(quotes[0].price, "3200.10") == 0);
  assert(quotes[1].valid);
  assert(std::strcmp(quotes[1].code, "000300") == 0);
  assert(std::strcmp(quotes[1].changePct, "-0.26") == 0);
  assert(!quotes[2].valid);
  assert(!quotes[7].valid);
}

static void testPartialMergePreservesLastSuccessfulQuotes() {
  StockInfo current[STOCK_COUNT] = {};
  current[0].valid = true;
  std::strcpy(current[0].code, "000001");
  std::strcpy(current[0].price, "old-price");

  StockInfo fresh[STOCK_COUNT] = {};
  fresh[1].valid = true;
  std::strcpy(fresh[1].code, "000300");
  std::strcpy(fresh[1].price, "new-price");

  assert(mergeStockQuotes(current, fresh, STOCK_COUNT) == 1);
  assert(std::strcmp(current[0].price, "old-price") == 0);
  assert(std::strcmp(current[1].price, "new-price") == 0);
}

static void testOneResponsePopulatesDuplicateConfiguredSlots() {
  char duplicateCodes[STOCK_COUNT][STOCK_CODE_SIZE] = {};
  for (size_t i = 0; i < STOCK_COUNT; ++i) {
    std::strcpy(duplicateCodes[i], CODES[i]);
  }
  std::strcpy(duplicateCodes[1], CODES[0]);

  std::string payload = makeRecord("sh000001", "000001", "3200.10", "0.32");
  StockInfo quotes[STOCK_COUNT] = {};
  size_t parsed = parseTencentBatch(payload.c_str(), duplicateCodes,
                                    quotes, STOCK_COUNT);

  assert(parsed == 2);
  assert(quotes[0].valid);
  assert(quotes[1].valid);
  assert(std::strcmp(quotes[0].price, quotes[1].price) == 0);
}

static void testRecordLongerThan512BytesStillParses() {
  std::string payload = "v_sh512760=\"1~";
  payload += std::string(600, 'N');
  payload += "~512760~1.395";
  for (int field = 4; field < 32; ++field) {
    payload += "~0";
  }
  payload += "~-3.66~\";\n";

  StockInfo quotes[STOCK_COUNT] = {};
  size_t parsed = parseTencentBatch(payload.c_str(), CODES,
                                    quotes, STOCK_COUNT);

  assert(parsed == 1);
  assert(quotes[6].valid);
  assert(std::strcmp(quotes[6].code, "512760") == 0);
  assert(std::strcmp(quotes[6].price, "1.395") == 0);
  assert(std::strcmp(quotes[6].changePct, "-3.66") == 0);
}

int main() {
  testStockCodeValidationAndNormalization();
  testBatchQueryConstruction();
  testAllEightRecordsMapByCodeWhenReordered();
  testMalformedMissingDuplicateAndUnknownRecordsAreIsolated();
  testPartialMergePreservesLastSuccessfulQuotes();
  testOneResponsePopulatesDuplicateConfiguredSlots();
  testRecordLongerThan512BytesStillParses();
  std::cout << "stock_logic tests passed\n";
  return 0;
}
