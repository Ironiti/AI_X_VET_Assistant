# Как запустить бота:

## Подключение к серверу:

```bash
ssh root@147.45.214.10
```

**Если получили ошибку** - возможно лагануло подключение (не всегда порт принимает, есть микро лаги, стоит попробовать ещё несколько раз).
Как вариант проверки порта - пинг

```bash
ping 147.45.214.10
```

Если всё ок - вводим пароль (пользователь SSH ключа) / ключевую фразу (владелец SSH ключа)

Пароль от сервера:
```
ta1xyx@1?V7DyG
```

Ключевая фраза от сервера (если запрашивается не пароль):
```
Не настроил пока что
```

## Первая настройка сервера (1 раз при запуске/перезапуске сервера):

```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y python3 python3-pip python3-venv screen git
sudo apt install -y htop curl unzip net-tools
```

## Запускаем бота:

```bash
cd ~
```

```bash
git clone https://dimi3tru:ghp_XXXXXXXXXXXXXXXXXXXXXXX@github.com/dimi3tru/SBER_bot_cases_rag_lite_version.git

```

```bash
cd AI_VET_UNION_BOT
```

```bash
python -m venv venv
source venv/bin/activate
```

```bash
pip install -r requirements.txt
```

### Добавить .env файл с токенами:
```bash
nano .env
```

Далее вводим токены:
API_1=...
API_2 = '...' (другой вариант записи)

Сохраняем через Ctrl+O, Enter, затем Ctrl+X для выхода.

Проверка содержимого:
```bash
cat .env
```

### Напрямую:

```bash
python bot_main_simple.py
```

### Запуск сессии после пула через `screen`:

```bash
screen -S bot_session
python bot_main_simple.py
```

Завершить `screen`:

- `Ctrl+A`, потом `D` — отсоединиться, чтобы закрыть терминал
- `screen -r bot_session` — вернуться (зайти в сессию после перехода в директорию проекта на сервере)
- `exit` — завершить текущую сессию после `Ctrl+C`

