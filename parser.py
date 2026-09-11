import re
from datetime import datetime

import pandas as pd
from bs4 import BeautifulSoup

import re

def parse_lead_time_days(lead_time_text):

    if not lead_time_text:
        return 1

    text = lead_time_text.strip().upper()

    # If part is in stock, lead time becomes 1
    # AeroBuy will only accept a whole number >0 as a valid lead time.
    # Standard Rotabull clauses are varied, e.g. "2 WKS" or "30-45 days".
    # Below code interprests and standardises these clauses

    if text.startswith("STOCK"):
        return 1

    if text.startswith("STK"):
        return 1

    numbers = [
        int(n)
        for n in re.findall(r"\d+", text)
    ]

    if not numbers:
        return 1

    value = min(numbers)

    if any(
        unit in text
        for unit in [
            "WK",
            "WKS",
            "WEEK",
            "WEEKS"
        ]
    ):
        return max(1, value * 7)

    if any(
        unit in text
        for unit in [
            "MO",
            "MOS",
            "MONTH",
            "MONTHS"
        ]
    ):
        return max(1, value * 30)

    if any(
        unit in text
        for unit in [
            "DAY",
            "DAYS",
            "DY",
            "DYS"
        ]
    ):
        return max(1, value)

    # If Unknown unit
    # Treat numeric value as days

    return max(1, value)

# Some AeroBuy fields only accept alphanumeric characters, others allow for certain special characters

def strip_special(text):
    return re.sub(r"[^A-Za-z0-9]+", "", str(text))

def strip_special2(text):
    return re.sub(r"[^A-Za-z0-9 .-]+", "", str(text))

def parse_tagged_by(text):

    match = re.match(r"(.+?)\s+on\s+(.+)", text)

    if not match:
        return text, ""

    supplier = match.group(1).strip()
    date_text = match.group(2).strip()

    try:
        tag_date = datetime.strptime(
            date_text,
            "%b %d, %Y"
        ).strftime("%Y-%m-%d")
    except:
        tag_date = date_text

    return supplier, tag_date


def extract_rfq(text):

    match = re.search(
        r"RFQ\s+#\s*(\S+)",
        text
    )

    return match.group(1) if match else ""

#Below function will prevent AeroBull from crashing if a queried element doesn't exist

def safe_text(node):

    if node:
        return node.get_text(strip=True)

    return ""
    
def find_field_value(container, label):

    for td in container.find_all("td"):

        text = td.get_text(strip=True)

        if text == label:

            sibling = td.find_next_sibling("td")

            if sibling:
                return sibling.get_text(strip=True)

    return ""
    
def get_label_value(container, label):

    for td in container.find_all("td"):

        text = td.get_text(
            " ",
            strip=True
        )

        if text == label:

            sibling = td.find_next_sibling("td")

            if sibling:
                return sibling.get_text(
                    " ",
                    strip=True
                )

    return ""
    
CONDITION_MAP = {
    "OH": "Overhauled",
    "SV": "Used/Serviceable",
    "NE": "New",
    "AR": "As Removed",
    "FN": "New"
}    

def parse_rotabull(
    text,
    html,
    include_paperwork_url=True
):
    rfq_number = extract_rfq(text)

    soup = BeautifulSoup(
        html,
        "html5lib"
    )

    rows = []

    line_items = soup.find_all(
        "tr",
        class_="line-item"
    )

    for item in line_items:

        part_number = safe_text(
            item.find(
                "td",
                class_="part-number"
            )
        )

        condition_code = safe_text(
            item.find(
                "td",
                class_="condition-code"
            )
        )

        quantity_text = safe_text(
            item.find(
                "td",
                class_="quantity"
            )
        )

        lead_time_text = safe_text(
            item.find(
                "td",
                class_="lead-time"
            )
        )

        price_text = safe_text(
            item.find(
                "td",
                class_="unit-price"
            )
        )

        quantity_match = re.search(
            r"(\d+)",
            quantity_text
        )

        quantity = (
            quantity_match.group(1)
            if quantity_match
            else ""
        )

#Price must not include any special characters

        price = (
            price_text
            .replace("$", "")
            .replace(",", "")
        )

        description = ""
        serial = ""
        trace = ""
        tagged_by = ""
        tag_date = ""

        paperwork = []

        current = item

        while True:

#Run the find_next_sibling loop until "line-item", indicating next PN in quote.

            current = current.find_next_sibling("tr")

            if current is None:
                break

            classes = current.get("class", [])

            if "line-item" in classes:
                break

            description = (
                get_label_value(
                    current,
                    "Description:"
                )
                or description
            )

            serial = (
                get_label_value(
                    current,
                    "Serial Number:"
                )
                or serial
            )

            trace = (
                get_label_value(
                    current,
                    "Trace To:"
                )
                or trace
            )

            tagged_text = get_label_value(
                current,
                "Tagged by:"
            )

            if tagged_text:

                tagged_by, tag_date = (
                    parse_tagged_by(
                        tagged_text
                    )
                )


            for a in current.find_all("a"):

                href = a.get("href")

                if (
                    href and
                    "rotabull-prod-attachments"
                    in href
                ):
                    paperwork.append(href)

#If condition code is unrecgonized, set it to "Unknown"

        condition = CONDITION_MAP.get(
            condition_code,
            "Unknown"
        )

# Current warranty handling is SV = 180, anything else = 365
# For future implemations, maybe include a library of Honeywell Distribution parts and set warranty at 1440 if part number belongs to that library

        warranty = (
            180
            if condition ==
            "Used/Serviceable"
            else 365
        )

        remarks_parts = []

#In 'Supplier Remarks', we can include any relevant information. Here I add the stock location (or lead time if not in stock), trace details and the
#URL of the first paperwork attachment. The user can enable or disable inclusion of the paperwork URL with the checkbox in AeroBull

        if lead_time_text:
            remarks_parts.append(f"Lead Time: {lead_time_text}")

        if trace:
            remarks_parts.append(f"Trace: {strip_special2(trace)}")

        if (
            include_paperwork_url
            and len(paperwork) > 0
        ):
            remarks_parts.append(
                f"Paperwork: {paperwork[0]}"
            )

        remarks = ", ".join(remarks_parts)
        remarks = remarks.replace("/", "\\")

        row = {
            "Quote Number": rfq_number,
            "Part Number": part_number,
            "Keyword":
                strip_special(description)[:8],
            "Quantity": quantity,
            "Unit": "EA",
            "Price": price,
            "Currency": "USD",
            "Price Held Firm": 14,
            "Lead Time Days":
                parse_lead_time_days(
                    lead_time_text
                ),
            "Serial Number": serial,
            "Condition": condition,
            "Warranty Period": warranty,
            "Warranty Ref Code": "D",
            "Warranty Type Code": "O",
            "Supplier Remarks": remarks,
            "Comments": "",
            "Tagged By": strip_special2(tagged_by)[:30],
            "Tag Date": tag_date,
            
            # Paperwork columns 2 and 3 exist in case of future implementation
            
            "Paperwork1":
                paperwork[0]
                if len(paperwork) > 0 else "",
            "Paperwork2":
                paperwork[1]
                if len(paperwork) > 1 else "",
            "Paperwork3":
                paperwork[2]
                if len(paperwork) > 2 else ""
        }

        rows.append(row)

    return pd.DataFrame(rows)