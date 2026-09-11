
#used to get the filepath for downloaded ppw
import os
import sys
import hmac
import secrets

from flask import Flask, jsonify, request, send_file

app = Flask(__name__)

# Shared secret for the local API. Generated automatically on first run and
# persisted, so nothing on the machine besides AeroEdge can call the API -
# without this, any other process or browser tab reaching 127.0.0.1:8765
# could read quote data, trigger imports, or pull files off disk.
#
# AeroEdge is loaded unpacked straight out of the AeroEdge/ folder next to
# this file (it isn't installed from the Web Store), so the token is handed
# to it automatically by writing it into AeroEdge/token.json on every start -
# no manual pairing step required.

import json

# When packaged as a standalone PyInstaller executable, __file__ resolves to
# a temporary extraction folder that's wiped after the process exits - not
# where the .exe itself sits. sys.executable is the reliable one there.

if getattr(sys, "frozen", False):
    APP_DIR = os.path.dirname(sys.executable)
else:
    APP_DIR = os.path.dirname(os.path.abspath(__file__))

TOKEN_PATH = os.path.join(APP_DIR, "aerobull_token.txt")

# Some machines run AeroBull from a location the current user can't write to
# (Program Files, a read-only network share). Fall back to a per-user folder
# rather than crashing on import before the window even opens.

FALLBACK_TOKEN_PATH = os.path.join(
    os.getenv(
        "LOCALAPPDATA",
        os.path.expanduser("~")
    ),
    "AeroBull",
    "aerobull_token.txt"
)

EXTENSION_TOKEN_PATH = os.path.join(APP_DIR, "AeroEdge", "token.json")

def _read_token(path):

    if os.path.exists(path):

        with open(path, "r") as f:

            existing = f.read().strip()

            if existing:
                return existing

    return None

def _load_or_create_token():

    existing = (
        _read_token(TOKEN_PATH)
        or _read_token(FALLBACK_TOKEN_PATH)
    )

    if existing:
        return existing

    token = secrets.token_hex(32)

    try:

        with open(TOKEN_PATH, "w") as f:
            f.write(token)

    except OSError as e:

        print(
            "Couldn't write token next to aerobull_api.py "
            f"({e}); using per-user folder instead."
        )

        os.makedirs(
            os.path.dirname(FALLBACK_TOKEN_PATH),
            exist_ok=True
        )

        with open(FALLBACK_TOKEN_PATH, "w") as f:
            f.write(token)

    return token

def _publish_token_to_extension(token):

    try:

        with open(EXTENSION_TOKEN_PATH, "w") as f:
            json.dump({"token": token}, f)

    except OSError as e:

        print(
            "Couldn't write AeroEdge/token.json "
            f"({e}); AeroEdge won't be able to authenticate "
            "until this folder is writable."
        )

API_TOKEN = _load_or_create_token()
_publish_token_to_extension(API_TOKEN)

@app.before_request
def require_token():

    if request.method == "OPTIONS":
        return

    supplied = request.headers.get("X-AeroBull-Token", "")

    if not hmac.compare_digest(supplied, API_TOKEN):

        return jsonify({
            "error": "Unauthorized"
        }), 401

selected_row_data = {}

latest_rotabull_import = {
"html": ""
}

no_quote_parts = []

paperwork_settings = {
    "folder": ""
}

part_lookup_request = {
    "part_number": "",
    "result": None
}

manual_selection_required = {
    "required": False
}

@app.route("/paperworkfile")
def paperwork_file():

    filepath = request.args.get(
        "filepath",
        ""
    )

    folder = paperwork_settings["folder"]

# Paperwork can only be served from the folder the user picked in
# "Download Paperwork" - this stops the filepath argument from being used
# to read arbitrary files off the machine (path traversal).

    if not folder:

        return jsonify({
            "found": False
        }), 404

    folder_real = os.path.realpath(folder)
    filepath_real = os.path.realpath(filepath) if filepath else ""

    if (
        not filepath_real
        or os.path.commonpath(
            [folder_real, filepath_real]
        ) != folder_real
    ):

        return jsonify({
            "found": False
        }), 404

    if not os.path.exists(filepath_real):

        return jsonify({
            "found": False
        }), 404

    return send_file(
        filepath_real,
        as_attachment=False
    )

@app.route(
    "/findpaperwork",
    methods=["POST"]
)

#As all downloaded ppw is saved as 'partnumber_serialnumber_1', this convention is used to find and send the paperwork for a PN when requested by AeroEdge

def find_paperwork():

    part_number = (
        request.json.get(
            "partNumber",
            ""
        ).strip()
    )

    serial_number = (
        request.json.get(
            "serialNumber",
            ""
        ).strip()
    )
    
    folder = (
        paperwork_settings[
            "folder"
        ]
    )
    
    print("Part:", part_number)
    print("Serial:", serial_number)
    print("Folder:", folder)


    if not folder:

        return jsonify({
            "found": False
        })

    filename = (
        f"{part_number}_"
        f"{serial_number}_1.pdf"
    )

    filepath = os.path.join(
        folder,
        filename
    )
    
    print("Checking:", filepath)
    print("Exists:", os.path.exists(filepath))

    if os.path.exists(filepath):

        return jsonify({
            "found": True,
            "filename": filename,
            "filepath": filepath
        })

    return jsonify({
        "found": False
    })
    

@app.route(
    "/importrotabull",
    methods=["POST"]
)
def import_rotabull():

    latest_rotabull_import["html"] = (
        request.json.get("html", "")
    )

    print("ROTABULL IMPORT RECEIVED")
    print(
        len(latest_rotabull_import["html"])
    )

    return jsonify({
        "success": True
    })
    
   

@app.route("/status")
def status():

    return jsonify({
        "message": "Connected"
    })


@app.route("/selectedrow")
def selectedrow():

    return jsonify(selected_row_data)
    
@app.route(
    "/findpart",
    methods=["POST"]
)
def find_part():

    part_number = (
        request.json.get(
            "partNumber",
            ""
        ).strip()
    )

    part_lookup_request[
        "part_number"
    ] = part_number

    part_lookup_request[
        "result"
    ] = None
    
    manual_selection_required["required"] = False

    return jsonify({
        "success": True
    })
    
@app.route(
    "/findpartresult"
)
def find_part_result():

    return jsonify(
        part_lookup_request["result"] or {}
    )
    
@app.route("/manualselection")
def manual_selection():

    return jsonify({
        "required":
            manual_selection_required[
                "required"
            ]
    })
    
@app.route("/selectedrowdata")
def selected_row_data_route():

    manual_selection_required[
        "required"
    ] = False

    return jsonify(
        selected_row_data
    )
    
@app.route("/noquoteparts")
def no_quote_parts_route():

    return jsonify(
        no_quote_parts
    )