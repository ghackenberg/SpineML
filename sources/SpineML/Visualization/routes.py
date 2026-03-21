from tkinter import Tk, Canvas, ROUND, mainloop
from random import randint

from ..Configuration import Layout, Order, Corridor, Machine

from ..controller.calculate import calculateMachineSequences

canvas_width = 800
canvas_height = 600

padding = 50

unit = 10

def visualizeRoute(layout: Layout, order: Order) -> None:

    # Compute routes

    routes = calculateMachineSequences(order.product_type, layout)

    num_routes = len(routes)

    # Count corridors and machines

    num_corridors = len(layout.corridors)
    num_machines = 0

    for corridor in layout.corridors:
        num_machines = max(num_machines, len(corridor.machines_left))
        num_machines = max(num_machines, len(corridor.machines_right))

    print(num_corridors)
    print(num_machines)

    step_y = (canvas_height - padding * 2) / (num_corridors + 1)
    step_x = (canvas_width - padding * 2) / (num_machines * 2 + 3)

    # Initialize window

    root = Tk()
    root.title('SpineML - Route visualization')

    # Initialize canvas

    canvas = Canvas(root, width=canvas_width, height=canvas_height)
    canvas.pack()
    
    # Draw corridors

    canvas.create_rectangle(canvas_width / 2 - unit / 2, padding, canvas_width / 2 + unit / 2, canvas_height - padding, fill='lightgray', outline='')

    y_values: dict[Corridor, float] = {}

    for i in range(num_corridors):
        corridor = layout.corridors[i]

        y = padding + step_y * (i + 1)
        y0 = y - unit / 2
        y1 = y + unit / 2

        y_values[corridor] = y

        # Draw left arm
        if len(corridor.machines_left) > 0:
            x1 = canvas_width / 2 - step_x
            x0 = x1 - step_x * len(corridor.machines_left)

            canvas.create_rectangle(x0, y0, x1, y1, fill='lightgray', outline='')
        
        # Draw right arm
        if len(corridor.machines_right) > 0:
            x0 = canvas_width / 2 + step_x
            x1 = x0 + step_x * len(corridor.machines_right)

            canvas.create_rectangle(x0, y0, x1, y1, fill='lightgray', outline='')
    
    # Draw machines

    x_values: dict[Machine, float] = {}

    for i in range(num_corridors):
        corridor = layout.corridors[i]

        y = y_values[corridor]
        y0 = y - unit * 2
        y1 = y + unit * 2

        for j in range(len(corridor.machines_left)):
            machine = corridor.machines_left[j]

            x = canvas_width / 2 - step_x * (j + 2)
            x0 = x - unit * 2
            x1 = x + unit * 2

            x_values[machine] = x

            canvas.create_rectangle(x0, y0, x1, y1, fill='gray', outline='')
        
        for j in range(len(corridor.machines_right)):
            machine = corridor.machines_right[j]

            x = canvas_width / 2 + step_x * (j + 2)
            x0 = x - unit * 2
            x1 = x + unit * 2

            x_values[machine] = x

            canvas.create_rectangle(x0, y0, x1, y1, fill='gray', outline='')
    
    # Draw routes

    for i in range(num_routes):
        route = routes[i]

        x0 = canvas_width / 2
        y0 = padding

        width = (unit / 2 - 1) * (num_routes - i) / num_routes + 1

        b = ("%02x" % 0)
        g = ("%02x" % 0)
        r = ("%02x" % int(i / num_routes * 255))

        color = '#' + r + g + b

        for machine in route:
            corridor = machine.corridor

            x1 = x_values[machine]
            y1 = y_values[corridor]

            canvas.create_line(x0, y0, x1, y1, fill=color, width=width, capstyle=ROUND, joinstyle=ROUND)

            canvas.create_oval(x1 - width * 2, y1 - width * 2, x1 + width * 2, y1 + width * 2, fill=color, outline='')

            x0 = x1
            y0 = y1

        x1 = canvas_width / 2
        y1 = canvas_height - padding

        canvas.create_line(x0, y0, x1, y1, fill=color, width=width, capstyle=ROUND, joinstyle=ROUND)


    mainloop()
