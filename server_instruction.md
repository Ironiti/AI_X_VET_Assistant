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
git clone git@github.com:dimi3tru-other-projects/AI_VET_Assistant.git

```

```bash
cd AI_VET_Assistant
```

```bash
python -m venv venv
source venv/bin/activate
```

```bash
pip install -r requirements-unix.txt
```

Если процесс killed - скорее всего не хватило ОЗУ. Тогда можно попробовать вот так (создание файла подкачки, swap):
```bash
# Создаем файл подкачки
sudo fallocate -l 2G /swapfile

# Настраиваем права
sudo chmod 600 /swapfile

# Форматируем как swap
sudo mkswap /swapfile

# Включаем swap
sudo swapon /swapfile

# Делаем постоянным (добавляем в fstab)
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
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
python main.py
```

### Запуск сессии после пула через `screen`:

```bash
screen -S bot_session
python main.py
```

Завершить `screen`:

- `Ctrl+A`, потом `D` — отсоединиться, чтобы закрыть терминал
- `screen -r bot_session` — вернуться (зайти в сессию после перехода в директорию проекта на сервере)
- `exit` — завершить текущую сессию после `Ctrl+C`

