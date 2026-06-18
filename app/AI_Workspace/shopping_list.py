import tkinter as tk

class ShoppingList:
    def __init__(self):
        self.window = tk.Tk()
        self.window.title("Shopping List")

        # Input fields for shopping list items
        self.item_label = tk.Label(self.window, text="Item:")
        self.item_label.grid(row=0, column=0)
        self.item_entry = tk.Entry(self.window)
        self.item_entry.grid(row=0, column=1)

        self.price_label = tk.Label(self.window, text="Price:")
        self.price_label.grid(row=1, column=0)
        self.price_entry = tk.Entry(self.window)
        self.price_entry.grid(row=1, column=1)

        self.quantity_label = tk.Label(self.window, text="Quantity:")
        self.quantity_label.grid(row=2, column=0)
        self.quantity_entry = tk.Entry(self.window)
        self.quantity_entry.grid(row=2, column=1)

        # Button to add items to the list
        self.add_button = tk.Button(self.window, text="Add", command=self.add_item)
        self.add_button.grid(row=3, column=0, columnspan=2)

        # Text box to display the shopping list
        self.list_text = tk.Text(self.window, width=40, height=10)
        self.list_text.grid(row=4, column=0, columnspan=2)

    def add_item(self):
        item = self.item_entry.get()
        price = float(self.price_entry.get())
        quantity = int(self.quantity_entry.get())

        # Create a new line in the text box for each item
        self.list_text.insert(tk.END, f"{item} x {quantity} @ ${price:.2f} = ${price * quantity:.2f}\n")

        # Clear input fields
        self.item_entry.delete(0, tk.END)
        self.price_entry.delete(0, tk.END)
        self.quantity_entry.delete(0, tk.END)

    def run(self):
        self.window.mainloop()

if __name__ == "__main__":
    shopping_list = ShoppingList()
    shopping_list.run()