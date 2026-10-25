#include "stock_logic.h"

#include <string.h>

static const char* findBounded(const char* start,
                               const char* end,
                               char target) {
  while (start < end) {
    if (*start == target) return start;
    ++start;
  }
  return nullptr;
}

static bool copyField(const char* data,
                      const char* dataEnd,
                      int index,
                      char* out,
                      size_t outLen) {
  if (!data || !dataEnd || data > dataEnd || !out || outLen == 0) {
    return false;
  }

  int currentIndex = 0;
  const char* start = data;
  while (start < dataEnd && currentIndex < index) {
    const char* separator = findBounded(start, dataEnd, '~');
    if (!separator) return false;
    start = separator + 1;
    ++currentIndex;
  }
  if (currentIndex != index) return false;

  const char* end = findBounded(start, dataEnd, '~');
  if (!end) end = dataEnd;
  size_t length = (size_t)(end - start);
  if (length == 0 || length >= outLen) return false;

  memcpy(out, start, length);
  out[length] = '\0';
  return true;
}

bool isValidStockCode(const char* code) {
  if (!code || strlen(code) != 8) return false;
  if (strncmp(code, "sh", 2) != 0 && strncmp(code, "sz", 2) != 0) {
    return false;
  }
  for (size_t i = 2; i < 8; ++i) {
    if (code[i] < '0' || code[i] > '9') return false;
  }
  return true;
}

void normalizeStockCode(char* code, size_t len) {
  if (!code || len == 0) return;
  for (size_t i = 0; i < len && code[i]; ++i) {
    if (code[i] >= 'A' && code[i] <= 'Z') {
      code[i] = (char)(code[i] - 'A' + 'a');
    }
  }
  code[len - 1] = '\0';
}

bool buildStockQuery(const char codes[][STOCK_CODE_SIZE],
                     char* out,
                     size_t outLen) {
  if (!codes || !out || outLen == 0) return false;

  size_t used = 0;
  out[0] = '\0';
  for (size_t i = 0; i < STOCK_COUNT; ++i) {
    if (!isValidStockCode(codes[i])) return false;
    size_t codeLength = strlen(codes[i]);
    size_t required = codeLength + (i > 0 ? 1 : 0);
    if (used + required + 1 > outLen) {
      out[0] = '\0';
      return false;
    }
    if (i > 0) out[used++] = ',';
    memcpy(out + used, codes[i], codeLength);
    used += codeLength;
    out[used] = '\0';
  }
  return true;
}

size_t parseTencentBatch(const char* payload,
                         const char requestedCodes[][STOCK_CODE_SIZE],
                         StockInfo* quotes,
                         size_t quoteCount) {
  if (!payload || !requestedCodes || !quotes || quoteCount == 0) return 0;

  for (size_t i = 0; i < quoteCount; ++i) {
    quotes[i].valid = false;
  }

  size_t validCount = 0;
  const char* record = payload;
  while ((record = strstr(record, "v_")) != nullptr) {
    const char* recordEnd = strchr(record, ';');
    if (!recordEnd) recordEnd = record + strlen(record);

    const char* codeStart = record + 2;
    const char* equals = strchr(codeStart, '=');
    size_t responseCodeLength = equals ? (size_t)(equals - codeStart) : 0;
    bool requested = false;
    if (responseCodeLength == 8) {
      for (size_t i = 0; i < quoteCount; ++i) {
        if (strncmp(codeStart, requestedCodes[i], responseCodeLength) == 0
            && requestedCodes[i][responseCodeLength] == '\0') {
          requested = true;
        }
      }
    }

    const char* quoteStart = equals ? strchr(equals, '"') : nullptr;
    const char* quoteEnd = quoteStart ? strchr(quoteStart + 1, '"') : nullptr;
    if (requested && quoteStart && quoteEnd && quoteEnd <= recordEnd) {
      const char* data = quoteStart + 1;
      StockInfo parsed = {};
      if (copyField(data, quoteEnd, 2, parsed.code, sizeof(parsed.code))
          && copyField(data, quoteEnd, 3, parsed.price, sizeof(parsed.price))
          && copyField(data, quoteEnd, 32,
                       parsed.changePct, sizeof(parsed.changePct))) {
        parsed.valid = true;
        for (size_t i = 0; i < quoteCount; ++i) {
          if (!quotes[i].valid
              && strncmp(codeStart, requestedCodes[i],
                         responseCodeLength) == 0
              && requestedCodes[i][responseCodeLength] == '\0') {
            quotes[i] = parsed;
            ++validCount;
          }
        }
      }
    }

    if (*recordEnd == '\0') break;
    record = recordEnd + 1;
  }
  return validCount;
}

size_t mergeStockQuotes(StockInfo* current,
                        const StockInfo* fresh,
                        size_t quoteCount) {
  if (!current || !fresh) return 0;

  size_t merged = 0;
  for (size_t i = 0; i < quoteCount; ++i) {
    if (fresh[i].valid) {
      current[i] = fresh[i];
      ++merged;
    }
  }
  return merged;
}
