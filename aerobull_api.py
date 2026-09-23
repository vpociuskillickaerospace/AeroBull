
#used to get the filepath for downloaded ppw
import os
import hmac

from flask import Flask, jsonify, request, send_file

app = Flask(__name__)

# Shared secret for the local API, so nothing on the machine besides
# AeroEdge can call it - without this, any other process or browser tab
# reaching 127.0.0.1:8765 could read quote data, trigger imports, or pull
# files off disk.
#
# This is a FIXED value baked into both this file and AeroEdge/Popup.js at
# build time, not generated per-install. Earlier this was generated fresh
# on every AeroBull run and handed to AeroEdge by writing it into a
# token.json file next to this exe - that only worked while AeroEdge was
# loaded unpacked from that same folder. Once AeroEdge started being
# distributed via the Microsoft Edge Add-ons store, that stopped working:
# a Store-published extension runs from a frozen package Edge manages
# internally, which AeroBull has no way to write into and which doesn't
# change after publish - so every user's copy carried a stale/empty token
# that could never match what AeroBull generated for itself, and every
# request silently failed with 401 (silently, because the caller wasn't
# checking the response status - see Popup.js).
#
# Rotate this value only by changing it here AND in Popup.js's API_TOKEN
# together, then rebuilding/republishing both.

API_TOKEN = "eb2d5fcd3fe32c8e687ce718281c1ea21c5a65364824c094cadae6b8db3a753e"

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