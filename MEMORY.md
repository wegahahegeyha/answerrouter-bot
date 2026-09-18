# answerrouter_bot - память проекта

## Что это
Автоответчик в личных чатах владельца через Telegram Business ("автоматизация чатов").
Бот отвечает от имени владельца, играя его роль.

## Ключевые факты
- Бот: @answerrouter_bot (id 8737448767), token в .env
- Модель: openrouter/inclusionai/ling-3.0-flash-vl:free (мультимодальная)
- OpenRouter ключ: свой ключ OpenClaw, в .env
- Telegram Business = Bot API business connections: обновления business_message,
  отправка через sendMessage с business_connection_id
- Прокси: http://127.0.0.1:10809 (sing-box, как у OpenClaw)
- Файлы: bot.py, prompt.txt, .env (0600, не в гит)
- tmux сессия: answerrouter (живой лог через stdout)
- Путь: /root/.openclaw/workspace/answerrouter-bot/

## Поведение
- Промпт в prompt.txt: играет Влада, короткие живые ответы, без em dash, без списков
- Защита от инъекций: текст собеседника оборачивается в <message>...</message>,
  system-промпт запрещает выполнять инструкции из этих тегов
- Игнор: стикеры, голосовые, видео-заметки
- Фото: читается в RAM (file_bytes), base64 в запрос, на диск НЕ пишется
- Контекст: в RAM (ctx2), последние 10 сообщений от каждой стороны
- Сообщения, написанные владельцем вручную (from.id == business owner), сохраняются
  в историю как 'me', но на них не отвечаем

## Команды
- Запуск: tmux new-session -d -s answerrouter "python3 .../bot.py"
- Лог: tmux capture-pane -t answerrouter -p

## Статус
- 2026-09-17: создан, запущен. Модель указывается БЕЗ префикса openrouter/ -
  правильное имя: inclusionai/ling-3.0-flash-vl:free (с префиксом выдаёт 400).
  Модель reasoning-типа: content может быть null при обрезке - бот логирует и молчит.
- Команда /prompt (только от владельца, is_me): без аргументов шлёт промпт в код-блоке,
  /prompt текст - заменяет prompt.txt. Промпт читается заново на каждый ответ - рестарт не нужен.
- business owner id: 712783140. Работает, отвечает в чатах.
