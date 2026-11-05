// Lab Greeter: a very small sample mod. It counts how often the title screen opens and writes one log line each time.

function lab_greeter_state() {
    if (global[$ "__lab_greeter"] == undefined) {
        global.__lab_greeter = { title_visits: 0, last_message: "" };
    }
    return global.__lab_greeter;
}

// A pure function, so a test can check it without any game state.
function lab_greeter_message(_visits) {
    return _visits == 1 ? "Welcome to Mistria." : "Welcome back. Visit " + string(_visits) + ".";
}

function lab_greeter_on_title(_ctx) {
    var _state = lab_greeter_state();
    _state.title_visits += 1;
    _state.last_message = lab_greeter_message(_state.title_visits);
    mmapi_log_info("lab_greeter", _state.last_message);
}

mmapi_mod_declare("lab_greeter", "1.0.0");
mmapi_on("game.title_entered", lab_greeter_on_title);
