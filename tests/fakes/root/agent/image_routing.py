"""Fake of agent/image_routing.py: a model whose id contains "native" sees images natively."""


def decide_image_input_mode(provider, model, cfg, *, requested_provider=""):
    return "native" if "native" in str(model) else "text"
