# -*- coding: utf-8 -*-
def hello_fictional_languages():
    """
    Prints "Hello, World!" in various fictional languages.
    """
    greetings = {
        "Elvish": "Elen síla lúmenn' omentielvo, World!",
        "Klingon": "nuqneH, World!",
        "Dothraki": "M'athchomaroon, World!",
        "Valyrian": "Rytsas, World!",
    }

    for language, greeting in greetings.items():
        print(f"[{language}] {greeting}")


if __name__ == "__main__":
    hello_fictional_languages()
