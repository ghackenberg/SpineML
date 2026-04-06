from SpineML import *


def build_example():
    mt1 = MachineType("Machine type 1")
    mt2 = MachineType("Machine type 2")
    mt3 = MachineType("Machine type 3")

    tt1 = ToolType("Tool type 1", 2, 3, 10)
    tt2 = ToolType("Tool type 2", 1, 2, 9)
    tt3 = ToolType("Tool type 3", 3, 4, 12)

    pt1 = ProductType("Product type 1", 12, 12, 12, 5)
    pt2 = ProductType("Product type 2", 12, 24, 11, 10)
    pt3 = ProductType("Product type 3", 14, 15, 15, 6)
    pt4 = ProductType("Product type 4", 22, 23, 12, 7)
    pt5 = ProductType("Product type 5", 22, 23, 12, 7)
    pt6 = ProductType("Product type 6", 12, 24, 11, 10)

    OperationType("Operation 1", 1, 4, 0.15, mt1, tt1, pt1, pt2)
    OperationType("Operation 2", 1, 3, 0.20, mt1, tt2, pt3, pt2)
    OperationType("Operation 3", 1, 5, 0.11, mt2, tt3, pt2, pt4)
    OperationType("Operation 4", 1, 6, 0.11, mt2, tt2, pt2, pt5)
    OperationType("Operation 5", 1, 2, 0.11, mt3, tt1, pt2, pt6)

    scenario1 = Scenario("Scenario 1")
    scenario2 = Scenario("Scenario 2")
    scenario3 = Scenario("Scenario 3")

    route_order = Order("Order 1.1", 30, 11, 20, pt6, scenario1)
    Order("Order 1.2", 40, 15, 30, pt2, scenario1)
    Order("Order 2.1", 400, 25, 30, pt2, scenario2)
    Order("Order 3.1", 500, 15, 20, pt4, scenario3)
    Order("Order 3.2", 300, 25, 30, pt5, scenario3)

    layout1 = Layout("Layout 1", 10, 5, storage_capacity=1000)
    layout2 = Layout("Layout 2", 11, 3, storage_capacity=1000)
    layout3 = Layout("Layout 3", 11, 3, storage_capacity=1000)

    c1_1 = Corridor("Corridor 1.1", 500, 2, 3, layout1)
    c1_2 = Corridor("Corridor 1.2", 350, 2, 3, layout1)
    c1_3 = Corridor("Corridor 1.3", 200, 2, 3, layout1)
    c2_1 = Corridor("Corridor 2.1", 150, 2, 3, layout2)
    c2_2 = Corridor("Corridor 2.2", 150, 2, 3, layout2)
    c3_1 = Corridor("Corridor 3.1", 350, 2, 3, layout3)
    c3_2 = Corridor("Corridor 3.2", 120, 2, 3, layout3)
    c3_3 = Corridor("Corridor 3.3", 150, 2, 3, layout3)
    c3_4 = Corridor("Corridor 3.4", 300, 2, 3, layout3)

    Machine("Machine 1.1.1", mt1, c1_1, True, storage_capacity=1, storage_out_time=1, storage_in_time=1)
    Machine("Machine 1.1.2", mt1, c1_1, False, storage_capacity=1, storage_out_time=1, storage_in_time=1)
    Machine("Machine 1.2.1", mt2, c1_2, True, storage_capacity=1, storage_out_time=1, storage_in_time=1)
    Machine("Machine 1.2.2", mt3, c1_2, False, storage_capacity=1, storage_out_time=1, storage_in_time=1)
    Machine("Machine 1.3.1", mt1, c1_3, True, storage_capacity=1, storage_out_time=1, storage_in_time=1)
    Machine("Machine 1.3.2", mt1, c1_3, False, storage_capacity=1, storage_out_time=1, storage_in_time=1)

    Machine("Machine 2.1.1", mt1, c2_1, True, storage_capacity=1, storage_out_time=1, storage_in_time=1)
    Machine("Machine 2.1.2", mt1, c2_1, True, storage_capacity=1, storage_out_time=1, storage_in_time=1)
    Machine("Machine 2.1.3", mt3, c2_1, True, storage_capacity=1, storage_out_time=1, storage_in_time=1)
    Machine("Machine 2.1.4", mt2, c2_1, False, storage_capacity=1, storage_out_time=1, storage_in_time=1)
    Machine("Machine 2.2.1", mt1, c2_2, True, storage_capacity=1, storage_out_time=1, storage_in_time=1)

    Machine("Machine 3.1.1", mt1, c3_1, True, storage_capacity=1, storage_out_time=1, storage_in_time=1)
    Machine("Machine 3.1.2", mt1, c3_1, True, storage_capacity=1, storage_out_time=1, storage_in_time=1)
    Machine("Machine 3.1.3", mt1, c3_1, False, storage_capacity=1, storage_out_time=1, storage_in_time=1)
    Machine("Machine 3.2.1", mt3, c3_2, True, storage_capacity=1, storage_out_time=1, storage_in_time=1)
    Machine("Machine 3.2.2", mt2, c3_2, False, storage_capacity=1, storage_out_time=1, storage_in_time=1)
    Machine("Machine 3.2.3", mt2, c3_2, False, storage_capacity=1, storage_out_time=1, storage_in_time=1)
    Machine("Machine 3.4.1", mt3, c3_4, True, storage_capacity=1, storage_out_time=1, storage_in_time=1)

    return layout1, scenario1, layout1, route_order


def main() -> None:
    layout, scenario, route_layout, route_order = build_example()
    visualizeRoute(route_layout, route_order)
    simulate(layout, scenario)


if __name__ == "__main__":
    main()
