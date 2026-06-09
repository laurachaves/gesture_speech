import tkinter as tk

from src.Application import Application

root = tk.Tk()
root.title("MOVEMENT & SPEACH ANALYSER")
root.minsize(1500, 800)
root.geometry("1500x800")
root.attributes("-zoomed", True)

app = Application(master=root)
app.mainloop()