from SpineML import *


NUM_CORRIDORS = 8
NUM_MACHINES_LEFT = 4
NUM_MACHINES_RIGHT = 4


def build_example():
    mt1 = MachineType("Machine type 1")

    tt1 = ToolType("Tool type 1", 2, 3, 10)
    tt2 = ToolType("Tool type 2", 1, 2, 9)

    pt1 = ProductType("Product type 1", 12, 12, 12, 5)
    pt2 = ProductType("Product type 2", 12, 24, 11, 10)
    pt3 = ProductType("Product type 3", 14, 15, 15, 6)

    OperationType("Operation 1", 1, 5, 0.15, mt1, tt1, pt1, pt2)
    OperationType("Operation 2", 1, 4, 0.20, mt1, tt2, pt1, pt3)

    scenario = Scenario("Scenario 1")
    route_order = Order("Order 1.1", 10, 11, 20, pt2, scenario)
    Order("Order 1.2", 10, 11, 20, pt3, scenario)

    layout = Layout("Layout 1", 10, 5, storage_capacity=1000)

    for i in range(NUM_CORRIDORS):
        Corridor(f"Corridor {i + 1}", 200, 2, 3, layout)

    for i in range(NUM_CORRIDORS):
        for j in range(NUM_MACHINES_LEFT):
            Machine(
                f"Machine 1.{i + 1}.{j + 1}.left",
                mt1,
                CORRIDORS[i],
                True,
                storage_capacity=1,
                storage_out_time=1,
                storage_in_time=1,
            )
        for j in range(NUM_MACHINES_RIGHT):
            Machine(
                f"Machine 1.{i + 1}.{j + 1}.right",
                mt1,
                CORRIDORS[i],
                False,
                storage_capacity=1,
                storage_out_time=1,
                storage_in_time=1,
            )

    return layout, scenario, layout, route_order


def main() -> None:
    layout, scenario, route_layout, route_order = build_example()
    visualizeRoute(route_layout, route_order)
    simulate(layout, scenario, True)


if __name__ == "__main__":
    main()
