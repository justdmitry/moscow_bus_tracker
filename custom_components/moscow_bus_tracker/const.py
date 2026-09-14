DOMAIN = "moscow_bus_tracker"

CONF_API_KEY = "api_key"
CONF_UPDATE_INTERVAL = "update_interval"
CONF_SHOW_MISSED_INTERVAL = "show_missed"
CONF_NEWDAY_SHIFT = "newday_shift"

CONF_ROUTE_NUMBER = "route_number"
CONF_STOPS_QUERY = "stops_query"

CONF_ROUTE_ID = "route_id"
CONF_STOP_ID = "stop_id"

CONF_ROUTE_TYPE = "route_type"
CONF_ROUTE_TYPE_NAME = "route_type_name"
CONF_ROUTE_SHORT_NAME = "route_short_name"
CONF_ROUTE_LONG_NAME = "route_long_name"
CONF_STOP_NAME = "stop_name"

DEFAULT_UPDATE_INTERVAL_MINUTES = 60
DEFAULT_SHOW_MISSED_INTERVAL_MINUTES = 3
DEFAULT_NEWDAY_SHIFT_MINUTES = 180

## List of JavaScript modules to register
#JSMODULES: Final[list[dict[str, str]]] = [
#    {
#        "name": "Bus Card",
#        "filename": "bus-card.js",
#        "version": "0.0.1",
#    },
#    ## Add editor if needed
#    #{
#    #    "name": "Bus Card Editor",
#    #    "filename": "bus-card-editor.js",
#    #    "version": "0.0.1",
#    #},
#]