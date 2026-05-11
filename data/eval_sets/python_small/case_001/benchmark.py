from input import total_positive


def run(iterations: int = 10000) -> int:
    values = list(range(-50, 50))
    total = 0
    for _ in range(iterations):
        total += total_positive(values)
    return total


if __name__ == "__main__":
    run()
