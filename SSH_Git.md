## **1. SSH-доступ**

#### 1.1. Сгенерировать SSH-ключ:

```bash
ssh-keygen -t ed25519 -C "your comment"
```

#### 1.2. Скопировать публичный ключ:

```bash
cat ~/.ssh/id_ed25519.pub
```

Посмотреть хэш публичного ключа:
```bash
ssh-keygen -lf ~/.ssh/id_ed25519.pub
```

#### 1.3. Добавить ключ в GitHub:

* GitHub → Profile → **Settings** → **SSH and GPG keys** → **New SSH key** (https://github.com/settings/keys)
* Название: `Laptop SSH key` (например)
* Вставить содержимое `id_ed25519.pub`

#### 1.4. Проверить доступ:

```bash
ssh -T git@github.com
```

Успешный ответ:

```
Hi dimi3tru! You've successfully authenticated...
```

#### 1.5. Клонировать по SSH:

```bash
git clone git@github.com:dimi3tru-other-projects/AI_VET_Assistant.git
```
