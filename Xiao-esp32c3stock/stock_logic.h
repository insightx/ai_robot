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
size_t parseTencentBatch(const char* payload,
                         const char requestedCodes[][STOCK_CODE_SIZE],
                         StockInfo* quotes,
                         size_t quoteCount);
size_t mergeStockQuotes(StockInfo* current,
                        const StockInfo* fresh,
                        size_t quoteCount);
