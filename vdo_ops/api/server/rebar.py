from flask_rebar import Rebar

rebar = Rebar()
registry = rebar.create_handler_registry(prefix="/api")
