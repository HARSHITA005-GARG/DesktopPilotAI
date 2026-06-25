def calculate():
    while True:
        expression = input("Enter calculation (or 'q' to quit): ")
        if expression.lower() == 'q':
            break
        try:
            result = eval(expression)
            print(f"= {result}")
        except Exception as e:
            print(f"Error: {e}")

if __name__ == "__main__":
    calculate()