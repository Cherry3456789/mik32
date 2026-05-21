# MIK32 TinyML (готовый проект)

Проект включает полный pipeline:
1. Сборка прошивки (`firmware.bin`) под MIK32.
2. Генерация бинарных тестов (`.mktest`) на ПК.
3. Прошивка платы, отправка тестов по USB-serial (через отладчик), сбор результатов.

## 0) Зависимости
- Python 3.10+
- `pip install pyserial`
- PlatformIO CLI
- OpenOCD (или задайте `MIK32_UPLOAD_CMD`)

## 1) Сборка прошивки
```bash
python -m tools.runner build
```

## 2) Создание тестов
Случайные тесты 28x28 (784 байта):
```bash
python -m tools.testgen generate --output tests.mktest --count 32 --vec-len 784 --seed 42
```

Из CSV:
```bash
python -m tools.testgen generate --input dataset.csv --output tests.mktest --vec-len 784
```

Проверка формата:
```bash
python -m tools.testgen inspect --input tests.mktest
```

## 3) Прошивка платы
По умолчанию `tools.runner.mik32_upload` запускает OpenOCD.
Если у вас другой загрузчик, задайте команду:
```bash
export MIK32_UPLOAD_CMD="<ваша команда загрузчика>"
python -m tools.runner flash
```

## 4) Прогон тестов и сбор результатов
```bash
python -m tools.runner run-tests --port /dev/ttyACM0 --tests tests.mktest --out results.json
```

## Формат результатов
`results.json` содержит список тестов и предсказания (`prediction`) + вектор выходов (`logits`).
