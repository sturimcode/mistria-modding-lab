// Tests for Lab Greeter. Install this second mod in the lab only. Never ship it.
//
// The lab starts the game with MISTRIA_LAB=1 and MISTRIA_LAB_PROFILE=<profile name>. The tests register only
// when MISTRIA_LAB is set, and each one refuses to run unless saves are redirected to that profile.

function lab_greeter_tests_state() {
    if (global[$ "__lab_greeter_tests"] == undefined) {
        global.__lab_greeter_tests = { registered: false };
    }
    return global.__lab_greeter_tests;
}

function lab_greeter_tests_expected_profile() {
    return game_save_id + "/" + environment_get_variable("MISTRIA_LAB_PROFILE");
}

function lab_greeter_tests_guard() {
    if (CONFIG_DIRECTORY != lab_greeter_tests_expected_profile()) throw "Wrong profile: this test runs only in the lab";
}

// The lab polls this function until active is true. obj_ari exists once the player is in the world.
function lab_greeter_tests_status() {
    return { active: instance_exists(obj_ari), profile_ok: CONFIG_DIRECTORY == lab_greeter_tests_expected_profile() };
}

function lab_greeter_tests_in_lab_profile() {
    var _ok = CONFIG_DIRECTORY == lab_greeter_tests_expected_profile();
    return { passed: _ok, config_directory_is_lab_profile: _ok };
}

function lab_greeter_tests_message_format() {
    lab_greeter_tests_guard();
    var _first = lab_greeter_message(1), _later = lab_greeter_message(3);
    return { passed: _first == "Welcome to Mistria." && _later == "Welcome back. Visit 3.", first: _first, later: _later };
}

function lab_greeter_tests_hook_fired() {
    lab_greeter_tests_guard();
    var _state = lab_greeter_state();
    return { passed: _state.title_visits == 1 && _state.last_message == "Welcome to Mistria.", title_visits: _state.title_visits,
        last_message: _state.last_message };
}

function lab_greeter_tests_player_in_world() {
    lab_greeter_tests_guard();
    return { passed: instance_exists(obj_ari) };
}

// Writes a save in the lab profile, so a later run can use --mode continue.
function lab_greeter_tests_make_save() {
    lab_greeter_tests_guard();
    var _path = exact_save_path(Game.unique_identifier, true, 123456789);
    ARI.save_position = new LocationPosition(CURRENT_LOCATION_ID, Vec2(obj_ari.x, obj_ari.y));
    save_game(_path);
    return { passed: file_exists(_path), save_id: Game.unique_identifier };
}

function lab_greeter_tests_save_id() {
    lab_greeter_tests_guard();
    return { passed: instance_exists(obj_ari), save_id: Game.unique_identifier };
}

function lab_greeter_tests_tick() {
    var _state = lab_greeter_tests_state();
    if (_state.registered || environment_get_variable("MISTRIA_LAB") != "1") return;
    _state.registered = true;
    mmapi_debug_register_fn("lab_greeter_tests.status", lab_greeter_tests_status, {});
    mmapi_debug_register_fn("lab_greeter_tests.in_lab_profile", lab_greeter_tests_in_lab_profile, {});
    mmapi_debug_register_fn("lab_greeter_tests.message_format", lab_greeter_tests_message_format, {});
    mmapi_debug_register_fn("lab_greeter_tests.hook_fired", lab_greeter_tests_hook_fired, {});
    mmapi_debug_register_fn("lab_greeter_tests.player_in_world", lab_greeter_tests_player_in_world, {});
    mmapi_debug_register_fn("lab_greeter_tests.make_save", lab_greeter_tests_make_save, {});
    mmapi_debug_register_fn("lab_greeter_tests.save_id", lab_greeter_tests_save_id, {});
}

mmapi_mod_declare("lab_greeter_tests", "1.0.0");
mmapi_register(lab_greeter_tests_tick);
