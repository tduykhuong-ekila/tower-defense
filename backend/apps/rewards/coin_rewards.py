"""Server-only draw and public odds for knowledge mission coin bags."""

from secrets import randbelow

COIN_REWARD_DISTRIBUTION = ((20, 15), (25, 20), (30, 35), (40, 25), (60, 5))
EXPECTED_COIN_REWARD = sum(amount * chance for amount, chance in COIN_REWARD_DISTRIBUTION) / 100


def draw_coin_reward():
    ticket = randbelow(100)
    for amount, chance in COIN_REWARD_DISTRIBUTION:
        if ticket < chance:
            return amount
        ticket -= chance
    raise RuntimeError("Coin reward probabilities must sum to 100")


def public_coin_distribution():
    return [{"amount": amount, "probability_percent": chance} for amount, chance in COIN_REWARD_DISTRIBUTION]
