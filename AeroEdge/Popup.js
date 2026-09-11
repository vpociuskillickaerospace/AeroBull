
const API_BASE = "http://localhost:8765";

// AeroBull requires every request to carry a shared secret, so a stray
// webpage or process on the same machine can't poke the local API. AeroBull
// writes that secret into token.json (bundled next to this script) on every
// start, so it's picked up here with no pairing step needed.

let cachedToken = null;

async function getToken() {

    if (cachedToken !== null) {
        return cachedToken;
    }

    try {

        const response =
            await fetch(
                chrome.runtime.getURL(
                    "token.json"
                )
            );

        const data = await response.json();

        cachedToken = data.token || "";

    } catch (err) {

        cachedToken = "";
    }

    return cachedToken;
}

async function apiFetch(path, options = {}) {

    const token = await getToken();

    const headers = Object.assign(
        {},
        options.headers || {},
        { "X-AeroBull-Token": token }
    );

    return fetch(
        API_BASE + path,
        Object.assign(
            {},
            options,
            { headers }
        )
    );
}

document
.getElementById("testButton")
.addEventListener(
    "click",
    async () => {

        try {

            const response =
                await apiFetch(
                    "/selectedrow"
                );

            const row =
                await response.json();

            document
                .getElementById("status")
                .innerText =
                "Connected\n\n" +
                "Part Number: " +
                row["Part Number"];

        } catch (err) {

            document
                .getElementById("status")
                .innerText =
                err.toString();

            console.error(err);
        }
    }
);

async function populateAeroxchange(
    row,
    tabId
) {

    chrome.scripting.executeScript({

        target: {
            tabId: tabId
        },

        func: (data) => {

			const fieldMap = {
				"Quote Number": "RESPONSE_QUOTE_NUMBER",
				"Part Number": "PART_NUMBER",
				"Serial Number": "PART_SERIAL_NUMBER",
				"Keyword": "KEYWORD",
				"Quantity": "QUANTITY",
				"Unit": "UNIT",
				"Price": "PRICE",
				"Currency": "CURRENCY",
				"Price Held Firm": "PRICE_HELD_FIRM",
				"Lead Time Days": "LEADTIME",
				"Warranty Period": "WARRANTY1_VALUE",
				"Supplier Remarks": "SUPPLIER_REMARKS",
				"Comments": "DOCUMENT_REFERENCE",
				"Tagged By": "CERT_SOURCE",
				"Tag Date": "CERTIFICATION_DATE"
			};

			for (const [sourceField, targetField]
				of Object.entries(fieldMap)) {

				const value = data[sourceField];

				const element =
					document.querySelector(
						`[name="${targetField}"]`
					);

				if (element && value !== undefined) {

					element.value = value;

					element.dispatchEvent(
						new Event(
							"input",
							{ bubbles: true }
						)
					);

					element.dispatchEvent(
						new Event(
							"change",
							{ bubbles: true }
						)
					);
				}
			}

			// Condition Dropdown

			const conditionMap = {
				"New": "NU",
				"Overhauled": "OH",
				"Used/Serviceable": "US"
			};

			const conditionDropdown =
				document.querySelector(
					'[name="CONDITION_CODE"]'
				);

			if (conditionDropdown) {

				conditionDropdown.value =
					conditionMap[
						data["Condition"]
					];

				conditionDropdown.dispatchEvent(
					new Event(
						"change",
						{ bubbles: true }
					)
				);
			}
			
			// Static Warranty Fields

			const warrantyRef =
				document.querySelector(
					'[name="WARRANTY1_UOM"]'
				);

			if (warrantyRef) {

				warrantyRef.value = "Days";

				warrantyRef.dispatchEvent(
					new Event(
						"change",
						{ bubbles: true }
					)
				);
			}

			const warrantyType =
				document.querySelector(
					'[name="WARRANTY1_FROM"]'
				);

			if (warrantyType) {

				warrantyType.value =
					"From Origination";

				warrantyType.dispatchEvent(
					new Event(
						"change",
						{ bubbles: true }
					)
				);
			}
			
			let manufacturerCode = "AAAAA";

			const label =
				[...document.querySelectorAll("a")]
				.find(a =>
					a.textContent.includes(
						"Manufacturer Code"
					)
				);

			if (label) {

				const row = label.closest("tr");

				const cells =
					row.querySelectorAll("td");

				if (cells.length > 1) {

					const value =
						cells[1]
							.innerText
							.trim();

					if (value) {
						manufacturerCode = value;
					}
				}
			}
			const mfgField =
				document.querySelector(
					'[name="MFG_CODE"]'
				);

			if (mfgField) {

				mfgField.value =
					manufacturerCode;

				mfgField.dispatchEvent(
					new Event(
						"input",
						{
							bubbles: true
						}
					)
				);

				mfgField.dispatchEvent(
					new Event(
						"change",
						{
							bubbles: true
						}
					)
				);
			}

        },

        args: [row]

    });

}

async function uploadPaperwork(
    row,
    tabId
) {

    const paperworkResponse =
        await apiFetch(
            "/findpaperwork",
            {
                method: "POST",

                headers: {
                    "Content-Type":
                        "application/json"
                },

                body: JSON.stringify({
                    partNumber:
                        row["Part Number"],

                    serialNumber:
                        row["Serial Number"]
                })
            }
        );

    const paperwork =
        await paperworkResponse.json();

    if (!paperwork.found) {

        console.log(
            "No paperwork found."
        );

        return;
    }

    const pdfResponse =
        await apiFetch(
            "/paperworkfile?filepath=" +
            encodeURIComponent(
                paperwork.filepath
            )
        );

    const blob =
        await pdfResponse.blob();

    const file =
        new File(
            [blob],
            paperwork.filename,
            {
                type:
                    "application/pdf"
            }
        );

    await chrome.scripting.executeScript({

        target: {
            tabId: tabId
        },

        func: async (
            fileData,
            filename
        ) => {

            const bytes =
                new Uint8Array(
                    fileData
                );

            const file =
                new File(
                    [bytes],
                    filename,
                    {
                        type:
                            "application/pdf"
                    }
                );

            let fileInput = null;

            for (let i = 0; i < 40; i++) {

			var inputs = document.getElementsByTagName('input');

			for(var ii=0; ii<inputs.length; ii++){
			// Aeroxchange changes the name of the 'attach' input by removing attribute id:
			// 1st iteration: <input type="File" id="Attachment_id" name="file_0" userprompt="Attachment" size="50">
			// 2nd iteration: <input type="file" name="file_1" size="50">
			// 3rd iteration: <input type="file" name="file_2" size="50">
			// etc
				if(inputs[ii].getAttribute('type').toLowerCase() =='file'){
					
			    fileInput = inputs[ii];
				
				break;
				
				}
		    }
				   
				// Below code was previously used to target the 'attach' button, but failed on subsequent attempts due to the above Attachment_Id behaviour
               // fileInput =
                   // document.getElementById(
                      // "Attachment_id"
                   // );

                if (fileInput) {
                    break;
                }

                await new Promise(
                    r => setTimeout(
                        r,
                        250
                    )
                );
            }

            if (!fileInput) {

                console.log(
                    "Upload control not found."
                );

                return;
            }

            const dt =
                new DataTransfer();

            dt.items.add(file);

            fileInput.files =
                dt.files;

            fileInput.dispatchEvent(
                new Event(
                    "change",
                    {
                        bubbles: true
                    }
                )
            );

            console.log(
                "Upload attached"
            );

        },

        args: [
            [...new Uint8Array(
                await file.arrayBuffer()
            )],
            paperwork.filename
        ]

    });

}

document
.getElementById("fillButton")
.addEventListener(
    "click",
    async () => {

        try {

            const [tab] =
                await chrome.tabs.query({
                    active: true,
                    currentWindow: true
                });				

            const results =
                await chrome.scripting.executeScript({

					target: {
						tabId: tab.id
					},

					func: () => {

						const field =
							document.querySelector(
								'[name="PART_NUMBER"]'
							);

						return field
							? field.value.trim()
							: null;
					}

				});

			const partNumber =
				results[0].result;
				
				if (!partNumber) {

					document
						.getElementById("status")
						.innerText =
						"Part Number not found";

				return;
			}

			console.log(
				"Part Number:",
				partNumber
			);

			await apiFetch(
				"/findpart",
				{
					method: "POST",

					headers: {
						"Content-Type":
							"application/json"
					},

					body: JSON.stringify({
						partNumber
					})
				}
			);
			
			await new Promise(
				resolve => setTimeout(
					resolve,
					600
				)
			);
			
			const response =
				await apiFetch(
					"/findpartresult"
				);

			const result =
				await response.json();
				
			if (!result) {

				document
					.getElementById("status")
					.innerText =
					"No response from AeroBull";

				return;
			}

			if (result.multiple) {

				document
					.getElementById("status")
					.innerText =
					"Multiple matches found.\nUse Manual Selection mode.";

				return;
			}

			else if (!result.found) {

				document
					.getElementById("status")
					.innerText =
					"Part not found in AeroBull";

				return;
			}

			else {

				row = result.data;
			}
	
			await populateAeroxchange(
				row,
				tab.id
			);
	
			await uploadPaperwork(
				row,
				tab.id
			);

        } catch (err) {

            document
                .getElementById("status")
                .innerText =
                err.toString();

            console.error(err);
        }

    }
);

document
.getElementById("fillSelectedButton")
.addEventListener(
    "click",
    async () => {

        try {

            const response =
                await apiFetch(
                    "/selectedrow"
                );

            const row =
                await response.json();

            if (
                !row ||
                Object.keys(row).length === 0
            ) {

                document
                    .getElementById("status")
                    .innerText =
                    "No AeroBull row selected.";

                return;
            }

            const [tab] =
                await chrome.tabs.query({
                    active: true,
                    currentWindow: true
                });

			await populateAeroxchange(
				row,
				tab.id
			);
			
			await uploadPaperwork(
				row,
				tab.id
			);

        } catch (err) {

            document
                .getElementById("status")
                .innerText =
                err.toString();

            console.error(err);
        }

    }
);

document
.getElementById("importRotabull")
.addEventListener(
    "click",
    async () => {

        try {

            const [tab] =
                await chrome.tabs.query({
                    active: true,
                    currentWindow: true
                });

            if (
                !tab.url.includes(
                    "rotabull"
                )
            ) {

                document
                    .getElementById("status")
                    .innerText =
                    "Not on Rotabull";

                return;
            }

            const results =
                await chrome.scripting.executeScript({

                    target: {
                        tabId: tab.id
                    },

					func: () => {

						try {

							return window.frames[2]
								.document
								.body
								.innerHTML

						} catch (e) {

							return "";
						}
					}

                });

            const html =
                results[0].result;
				
			if (
				!html
					.toLowerCase()
					.includes(
						"quote from killick aerospace for rfq #"
					)
			) {

				document
					.getElementById("status")
					.innerText =
					"Import rejected.\nNot a Killick Aerospace RFQ.";

				return;
			}

            await apiFetch(
                "/importrotabull",
                {
                    method: "POST",

                    headers: {
                        "Content-Type":
                            "application/json"
                    },

                    body: JSON.stringify({
                        html: html
                    })
                }
            );

            document
                .getElementById("status")
                .innerText =
                "Rotabull Imported";

        } catch (err) {

            document
                .getElementById("status")
                .innerText =
                err.toString();
        }
    }
);

document
.getElementById("noQuoteButton")
.addEventListener(
    "click",
    async () => {

        try {

            const response =
                await apiFetch(
                    "/noquoteparts"
                );

            const noQuoteParts =
                await response.json();

            const [tab] =
                await chrome.tabs.query({
                    active: true,
                    currentWindow: true
                });

            const results =
                await chrome.scripting.executeScript({

                    target: {
                        tabId: tab.id
                    },

                    func: (parts) => {

                        let selectedCount = 0;

						const headerRow =
							document.querySelector("tr");

						const headers =
							[...headerRow.querySelectorAll("th")];

						const requestedPartCol =
							headers.findIndex(
								h =>
									h.innerText
									.trim()
									.includes(
										"Requested Part Number"
									)
							);
							
						const rows =
							document.querySelectorAll("tr");

                        for (const row of rows) {

                            const cells =
                                row.querySelectorAll(
                                    "td"
                                );

                            if (
                                cells.length < 4
                            ) {
                                continue;
                            }

							const requestedPart =
								cells[requestedPartCol]
									.innerText
									.trim();

                            if (
                                parts.includes(
                                    requestedPart
                                )
                            ) {

                                const checkbox =
                                    row.querySelector(
                                        'input[type="checkbox"]'
                                    );

                                if (
                                    checkbox &&
                                    !checkbox.checked
                                ) {

                                    checkbox.checked = true;

                                    checkbox.dispatchEvent(
                                        new Event(
                                            "change",
                                            {
                                                bubbles: true
                                            }
                                        )
                                    );

                                    selectedCount++;
                                }
                            }
                        }

                        return selectedCount;

                    },

                    args: [
                        noQuoteParts
                    ]

                });

            document
                .getElementById("status")
                .innerText =
                `${results[0].result} RFQ lines selected for no-quote`;

        } catch (err) {

            document
                .getElementById("status")
                .innerText =
                err.toString();

            console.error(err);

        }

    }
);