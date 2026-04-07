from ..Configuration import ProductType, OperationType, Layout, Machine

def calculateMachineSequencesFromOperationSequence(process: list[OperationType], layout: Layout) -> list[list[Machine]]:
    if len(process) > 0:
        result: list[list[Machine]] = []
        processStep = process.pop(0)
        for machine in processStep.machine_type.machines:
            if machine.corridor.layout == layout:
                routes = calculateMachineSequencesFromOperationSequence(process, layout)
                for route in routes:
                    route.insert(0, machine)
                    result.append(route)
        process.insert(0, processStep)
        return result
    else:
        return [[]]

def calculateMachineSequences(objectType: ProductType, layout: Layout):
    result: list[list[Machine]] = []
    processes = calculateOperationSequences(objectType)
    for process in processes:
        routes = calculateMachineSequencesFromOperationSequence(process, layout)
        for route in routes:
            exists = False
            for other_route in result:
                if all(x == y for x, y in zip(route, other_route)):
                    exists = True
                    break
            if not exists:
                result.append(route)
    return result


def calculateOperationSequences(objectType: ProductType):
    result: list[list[OperationType]] = []
    for operationType in objectType.producing_operations:
        prefixes = calculateOperationSequences(operationType.consumes_product_type)
        if not prefixes:
            result.append([operationType])
        else:
            for prefix in prefixes:
                prefix.append(operationType)
                result.append(prefix)
    return result


def calculateRemainingOperationSequences(
    current_object_type: ProductType,
    target_object_type: ProductType,
) -> list[list[OperationType]]:
    if current_object_type == target_object_type:
        return [[]]

    result: list[list[OperationType]] = []
    for operation_type in target_object_type.producing_operations:
        if operation_type.consumes_product_type == current_object_type:
            result.append([operation_type])
            continue

        prefixes = calculateRemainingOperationSequences(
            current_object_type,
            operation_type.consumes_product_type,
        )
        for prefix in prefixes:
            route = list(prefix)
            route.append(operation_type)
            result.append(route)
    return result
