class CustomEmojiManager:
    def __init__(self):
        self.emoji_ids = {
            'test_name': '5328315072840234225',
            'department': '5328315072840234225',
            'patient_preparation': '5328176289562004639',
            'biomaterial_type': '5327846616462291750',
            'primary_container_type': '5328063361986887821',
            'container_type': '5325856719459357092',
            'container_number': '5327851985171417222',
            'preanalytics': '5325585891706569447',
            'storage_temp': '5327963091680397149',
            'poss_postorder_container': '5327925321737995698',
            'form_link': '5327966179761881250',
            'additional_information_link': '5328169834226158945'
        }

    def format_message(self, text: str) -> str:
        for key in self.emoji_ids.keys():
            if key in text:
                emoji_html = f'<tg-emoji emoji-id="{self.emoji_ids[key]}"></tg-emoji>'
                text = text.replace(f'{key}', emoji_html)
        return text

# Инициализация
emoji_manager = CustomEmojiManager()