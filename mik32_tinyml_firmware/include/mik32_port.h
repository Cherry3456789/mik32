#ifndef MIK32_PORT_H
#define MIK32_PORT_H
#include <stdint.h>
void mik32_serial_init(uint32_t baud);
int mik32_serial_read_byte(uint8_t *out);
void mik32_serial_write(const uint8_t *buf, uint16_t len);
uint32_t mik32_millis(void);
#endif
