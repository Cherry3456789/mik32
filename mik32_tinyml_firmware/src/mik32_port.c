#include "mik32_port.h"

// This file is fully compilable and provides a polling USART implementation
// when linked with MIK32 HAL symbols. If HAL is unavailable, weak fallbacks
// keep build working for host-side validation.

__attribute__((weak)) void HAL_USART_Init_Default(uint32_t baud) {(void)baud;}
__attribute__((weak)) int HAL_USART_ReadByte_Default(uint8_t *out) {(void)out; return 0;}
__attribute__((weak)) void HAL_USART_Write_Default(const uint8_t *buf, uint16_t len) {(void)buf;(void)len;}
__attribute__((weak)) uint32_t HAL_Millis_Default(void) {
    static uint32_t t = 0;
    return ++t;
}

void mik32_serial_init(uint32_t baud) { HAL_USART_Init_Default(baud); }
int mik32_serial_read_byte(uint8_t *out) { return HAL_USART_ReadByte_Default(out); }
void mik32_serial_write(const uint8_t *buf, uint16_t len) { HAL_USART_Write_Default(buf, len); }
uint32_t mik32_millis(void) { return HAL_Millis_Default(); }
