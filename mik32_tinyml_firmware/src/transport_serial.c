#include "transport_serial.h"
#include <stdint.h>
#include <stdbool.h>

// Board-specific hooks. Provide real implementation in src/mik32_port.c
extern void mik32_serial_init(uint32_t baud);
extern int mik32_serial_read_byte(uint8_t *out); // 1=ok 0=no-data
extern void mik32_serial_write(const uint8_t *buf, uint16_t len);
extern uint32_t mik32_millis(void);

#define FRAME_MIN_LEN 8
#define RX_BUF_SZ 1200

void transport_init(void) { mik32_serial_init(115200); }

int transport_read(uint8_t *buf, uint16_t max_len) {
    uint16_t n = 0;
    while (n < max_len) {
        if (!mik32_serial_read_byte(&buf[n])) break;
        n++;
    }
    return (int)n;
}

void transport_write(const uint8_t *buf, uint16_t len) { mik32_serial_write(buf, len); }

bool transport_read_frame(uint8_t *frame_buf, uint16_t *frame_len, uint32_t timeout_ms) {
    uint8_t b;
    uint32_t start = mik32_millis();
    uint16_t idx = 0;
    uint16_t needed = FRAME_MIN_LEN;

    while ((mik32_millis() - start) < timeout_ms) {
        if (!mik32_serial_read_byte(&b)) continue;
        if (idx == 0 && b != 0xAA) continue;
        if (idx < RX_BUF_SZ) frame_buf[idx++] = b;
        else { idx = 0; continue; }

        if (idx >= 6) {
            uint16_t payload_len = (uint16_t)(frame_buf[4] | (frame_buf[5] << 8));
            needed = (uint16_t)(1 + 1 + 2 + 2 + payload_len + 2);
            if (needed > RX_BUF_SZ) { idx = 0; continue; }
        }
        if (idx >= needed) {
            *frame_len = idx;
            return true;
        }
    }
    return false;
}
