def total_positive(items):
    result = 0
    for item in items:
        if item > 0:
            result = result + item
    return result
