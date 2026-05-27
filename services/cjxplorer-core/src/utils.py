"""Общие утилиты бэкенда."""


def pluralize(n: int, one: str, few: str, many: str) -> str:
    """
    Склонение существительного по числительному (русский язык).

    Args:
        n: Число.
        one: Форма для 1 (скриншот).
        few: Форма для 2-4 (скриншота).
        many: Форма для 5+ (скриншотов).

    Returns:
        Строка вида '5 скриншотов'.
    """
    if 11 <= n % 100 <= 19:
        return f"{n} {many}"
    mod = n % 10
    if mod == 1:
        return f"{n} {one}"
    if 2 <= mod <= 4:
        return f"{n} {few}"
    return f"{n} {many}"
