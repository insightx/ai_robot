# Xiao-esp32c3stock

XIAO ESP32-C3 股票 + 天气信息终端（Nextion HMI / 可选 OLED）

## 快速开始

1. Arduino IDE → 开发板 **XIAO_ESP32C3**，USB CDC On Boot = **Enabled**
2. 复制凭证模板：
   ```bash
   cp secrets.h.example secrets.h
   ```
3. 编辑 `secrets.h`，填入 WiFi 与 OpenWeatherMap API Key
4. 打开 `xiao_esp32c3_stock.ino` 编译烧录
5. 串口 115200 查看 IP，浏览器打开 `http://<IP>/` 可修改 8 个股票代码

## 凭证说明

| 文件 | 是否入库 |
|------|----------|
| `secrets.h.example` | 是（模板） |
| `secrets.h` | **否**（本地私密） |

## 主要功能

- 8 只 A 股/指数行情（腾讯批量接口）+ OpenWeatherMap 天气 + NTP 北京时间
- 交易时段每 3 秒刷新，午休每 10 分钟刷新，非工作日不查询股票
- Nextion 使用 `t0`～`t23` 显示 8 组代码、价格和涨跌幅
- Web 配置页统一修改 8 个股票代码（NVS 持久化）

固件版本见 `xiao_esp32c3_stock.ino` 文件头。
