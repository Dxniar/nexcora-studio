"""Small shared locale catalogue for bot entry points and delivery messages."""
LANGUAGES = ('ru', 'en', 'kk')


def normalize_language(value) -> str:
    """Use Telegram's base language on first contact; retain a safe default."""
    if not isinstance(value, str): return 'ru'
    language = value.strip().lower().replace('_', '-').split('-', 1)[0]
    return language if language in LANGUAGES else 'ru'


MESSAGES = {
    'ru': {
        'bot.open_app': 'Открыть Nexcora Studio',
        'bot.language': 'Язык',
        'bot.choose_language': 'Выберите язык бота и Nexcora Studio.',
        'bot.language_saved': 'Язык сохранён. Он также будет использован в Nexcora Studio.',
        'bot.language_invalid': 'Выберите русский, английский или казахский язык.',
        'bot.private_chat': 'Откройте личный чат с ботом, чтобы перейти в Nexcora Studio.',
        'bot.portal': 'Nexcora Studio — обсудите задачу, согласуйте условия и следите за проектом.',
        'bot.owner': 'Nexcora Studio — кабинет владельца и очередь проектов.',
        'bot.my_id': 'Ваш Telegram ID: {user_id}',
        'bot.help': 'Откройте приложение, чтобы создать обращение, посмотреть проекты или связаться с исполнителем.',
        'notification.body': 'Проект #{project_id}: {event}.',
        'notification.open': 'Открыть проект',
        'notification.default': 'Есть обновление',
        'notification.submitted': 'Получено новое обращение',
        'notification.discuss': 'Началось обсуждение',
        'notification.publish_proposal': 'Предложение готово к согласованию',
        'notification.proposal_sent': 'Предложение готово к согласованию',
        'notification.accept_proposal': 'Условия согласованы',
        'notification.request_changes': 'Запрошены изменения условий',
        'notification.start': 'Работа над проектом началась',
        'notification.update': 'Добавлено обновление',
        'notification.deliver': 'Результат передан на приёмку',
        'notification.request_revision': 'Запрошены правки',
        'notification.accept_delivery': 'Результат принят',
        'notification.close': 'Обращение закрыто',
    },
    'en': {
        'bot.open_app': 'Open Nexcora Studio',
        'bot.language': 'Language',
        'bot.choose_language': 'Choose the language for the bot and Nexcora Studio.',
        'bot.language_saved': 'Language saved. Nexcora Studio will use this language too.',
        'bot.language_invalid': 'Choose Russian, English or Kazakh.',
        'bot.private_chat': 'Open a private chat with the bot to access Nexcora Studio.',
        'bot.portal': 'Nexcora Studio — discuss your task, agree on terms and track your project.',
        'bot.owner': 'Nexcora Studio — owner dashboard and project queue.',
        'bot.my_id': 'Your Telegram ID: {user_id}',
        'bot.help': 'Open the app to submit a request, view your projects or contact the developer.',
        'notification.body': 'Project #{project_id}: {event}.',
        'notification.open': 'Open project',
        'notification.default': 'There is an update',
        'notification.submitted': 'A new request has been received',
        'notification.discuss': 'The discussion has started',
        'notification.publish_proposal': 'The proposal is ready for approval',
        'notification.proposal_sent': 'The proposal is ready for approval',
        'notification.accept_proposal': 'The terms have been agreed',
        'notification.request_changes': 'Changes to the terms have been requested',
        'notification.start': 'Work on the project has started',
        'notification.update': 'An update has been added',
        'notification.deliver': 'The result is ready for review',
        'notification.request_revision': 'Revisions have been requested',
        'notification.accept_delivery': 'The result has been accepted',
        'notification.close': 'The request has been closed',
    },
    'kk': {
        'bot.open_app': 'Nexcora Studio ашу',
        'bot.language': 'Тіл',
        'bot.choose_language': 'Бот пен Nexcora Studio тілін таңдаңыз.',
        'bot.language_saved': 'Тіл сақталды. Nexcora Studio қолданбасында да осы тіл қолданылады.',
        'bot.language_invalid': 'Орыс, ағылшын немесе қазақ тілін таңдаңыз.',
        'bot.private_chat': 'Nexcora Studio қолданбасын ашу үшін ботпен жеке чатқа өтіңіз.',
        'bot.portal': 'Nexcora Studio — тапсырманы талқылаңыз, шарттарды келісіңіз және жобаның орындалуын бақылаңыз.',
        'bot.owner': 'Nexcora Studio — иесінің кабинеті және жобалар кезегі.',
        'bot.my_id': 'Сіздің Telegram ID: {user_id}',
        'bot.help': 'Өтінім жасау, жобаларды көру немесе орындаушымен байланысу үшін қосымшаны ашыңыз.',
        'notification.body': 'Жоба #{project_id}: {event}.',
        'notification.open': 'Жобаны ашу',
        'notification.default': 'Жаңарту бар',
        'notification.submitted': 'Жаңа өтінім алынды',
        'notification.discuss': 'Талқылау басталды',
        'notification.publish_proposal': 'Ұсыныс келісуге дайын',
        'notification.proposal_sent': 'Ұсыныс келісуге дайын',
        'notification.accept_proposal': 'Шарттар келісілді',
        'notification.request_changes': 'Шарттарды өзгерту сұралды',
        'notification.start': 'Жоба бойынша жұмыс басталды',
        'notification.update': 'Жаңарту қосылды',
        'notification.deliver': 'Нәтиже қабылдауға жіберілді',
        'notification.request_revision': 'Түзетулер сұралды',
        'notification.accept_delivery': 'Нәтиже қабылданды',
        'notification.close': 'Өтінім жабылды',
    },
}


def translate(key: str, language='ru', **params) -> str:
    """Unknown locales fall back safely; unknown message keys are programmer errors."""
    return MESSAGES[normalize_language(language)][key].format(**params)


def notification_event(kind: str, language='ru') -> str:
    key = 'notification.' + kind
    return translate(key if key in MESSAGES['ru'] else 'notification.default', language)
