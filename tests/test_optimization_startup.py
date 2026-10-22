from pathlib import Path
from types import SimpleNamespace

import optimization


class SessionState(dict):
    __getattr__ = dict.__getitem__
    __setattr__ = dict.__setitem__


def test_create_optimizer_loads_a_fresh_model_without_a_cache(monkeypatch):
    model_path = Path("example.py")
    models = []

    def load_model(path):
        assert path == model_path
        model = {"layout": object(), "scenario": object()}
        models.append(model)
        return model

    monkeypatch.setattr(optimization, "_resolve_model_path", lambda path: model_path)
    monkeypatch.setattr(optimization, "_load_model", load_model)
    monkeypatch.setattr(
        optimization, "_find_layout_and_scenario",
        lambda model, path: (model["layout"], model["scenario"]),
    )

    first = optimization.create_optimizer(str(model_path))
    second = optimization.create_optimizer(str(model_path))

    assert len(models) == 2
    assert first is not second
    assert first.simulation_runner is not second.simulation_runner
    assert first.global_evaluation is not second.global_evaluation
    assert first.simulation_runner.layout is models[0]["layout"]
    assert second.simulation_runner.scenario is models[1]["scenario"]


def make_interface(monkeypatch, clicked):
    model_path = Path("example.py")
    monkeypatch.setattr(optimization, "_resolve_model_path", lambda path: model_path)

    def button(label, *, disabled, on_click, args):
        if clicked and not disabled:
            on_click(*args)
        return clicked and not disabled

    interface = SimpleNamespace(
        session_state=SessionState(),
        title=lambda *args: None,
        caption=lambda *args: None,
        button=button,
    )
    monkeypatch.setattr(optimization, "st", interface)
    return interface, model_path


def test_showing_the_interface_does_not_create_an_optimizer(monkeypatch):
    interface, _ = make_interface(monkeypatch, clicked=False)

    def unexpected_creation(*args):
        raise AssertionError("Showing the interface must not reload the model")

    monkeypatch.setattr(optimization, "create_optimizer", unexpected_creation)
    optimization._streamlit_app()
    optimization._streamlit_app()

    assert not interface.session_state.optimization_state["running"]


def test_each_start_creates_a_new_optimizer_before_starting_the_worker(monkeypatch):
    interface, model_path = make_interface(monkeypatch, clicked=True)
    events = []

    def create_optimizer(path):
        assert path == str(model_path)
        optimizer = object()
        events.append(("create", optimizer))
        return optimizer

    def create_thread(target, *, daemon):
        def start():
            assert events[-1][0] == "create"
            events.append(("worker", events[-1][1]))
            interface.session_state.optimization_state["running"] = False

        return SimpleNamespace(start=start)

    monkeypatch.setattr(optimization, "create_optimizer", create_optimizer)
    monkeypatch.setattr(optimization.threading, "Thread", create_thread)
    optimization._streamlit_app()
    optimization._streamlit_app()

    assert [event[0] for event in events] == ["create", "worker", "create", "worker"]
    assert events[0][1] is not events[2][1]


def test_rerunning_the_interface_preserves_existing_display_data(monkeypatch):
    interface, _ = make_interface(monkeypatch, clicked=False)
    optimization._streamlit_app()
    state = interface.session_state.optimization_state
    state.update(error="Previous run failed", costs=[12.5])
    errors = []
    interface.error = errors.append

    optimization._streamlit_app()

    assert interface.session_state.optimization_state is state
    assert state["costs"] == [12.5]
    assert errors == ["Previous run failed"]
