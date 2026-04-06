from SpineML import *


def build_example():
    mt1 = MachineType("Machine type 1")
    mt2 = MachineType("Machine type 2")

    tt1 = ToolType("Tool type 1", 2, 3, 25)
    tt2 = ToolType("Tool type 2", 1, 2, 25)

    pt1 = ProductType("Product Type 1", 12, 12, 12, 5)
    pt2 = ProductType("Product Type 2", 12, 24, 11, 10)
    pt3 = ProductType("Product Type 3", 14, 15, 15, 6)

    OperationType("Operation 1", 1, 10, 0.15, mt1, tt1, pt1, pt2)
    OperationType("Operation 2", 1, 10, 0.20, mt2, tt2, pt1, pt3)

    scenario = Scenario("Scenario 1")

    route_order = Order("Order 1.1", 5, 11, 20, pt2, scenario)
    Order("Order 1.2", 5, 11, 20, pt3, scenario)

    layout = Layout("Layout 1", 10, 5, storage_capacity=1000)
    corridor = Corridor("Corridor 1.1", 200, 2, 3, layout)

    Machine(
        "Machine 1.1.1",
        mt1,
        corridor,
        True,
        storage_capacity=1,
        storage_out_time=1,
        storage_in_time=1,
    )
    Machine(
        "Machine 1.1.2",
        mt2,
        corridor,
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
