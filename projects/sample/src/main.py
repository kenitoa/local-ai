def total_positive(items):
    result = 0
    for item in items:
        if item > 0:
            result = result + item
    return result


if __name__ == "__main__":
    print(total_positive([1, -2, 3, 4]))
