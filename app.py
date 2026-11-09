
import streamlit as st
import pandas as pd
import re




def extract_invoice_fields(text):
    """Extract invoice fields and flag values that need review."""

    fields = {
        "Vendor": None,
        "Invoice Number": None,
        "Date": None,
        "Subtotal": None,
        "Discount": None,
        "Shipping": None,
        "Tax": None,
        "Total": None,
    }

    lines = [line.strip() for line in text.splitlines() if line.strip()]

   
    # Invoice number: require a specific invoice identifier label.
    invoice_patterns = [
        r"\bINVOICE\s+(?:NO\.?|NUMBER)\s*:?\s*([A-Za-z0-9]+(?:[-/][A-Za-z0-9]+)*)",
        r"\bINVOICE\s*#\s*:?\s*([A-Za-z0-9]+(?:[-/][A-Za-z0-9]+)*)",
        r"\bINVOICE\s*:\s*([A-Za-z0-9]+(?:[-/][A-Za-z0-9]+)*)",
        r"\bINVOICE\s+([A-Za-z0-9]+(?:[-/][A-Za-z0-9]+)*)",
    ]

    match = None

    for pattern in invoice_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            break

    if match:
        invoice_number = match.group(1).strip()

        invalid_values = {
            "undefined",
            "none",
            "null",
            "n/a",
            "na",
             "invoice",
        }

        if invoice_number.lower() not in invalid_values:
            fields["Invoice Number"] = invoice_number


    # Vendor: identify a suitable company name before OR after the invoice number.

    invoice_line_index = None

    # Find the invoice heading or invoice number line.
    for index, line in enumerate(lines):
        if re.search(r"\bINVOICE\b", line, re.IGNORECASE):
            invoice_line_index = index
            break

    # Check whether a candidate looks like a vendor name.
    def is_vendor_candidate(candidate):
        upper_candidate = candidate.upper()

        excluded_labels = (
            "INVOICE", "BILL TO:", "BILL TO", "SHIP TO:",
            "SHIP TO", "DATE:", "SHIP MODE:", "BALANCE DUE:",
            "SUBTOTAL:", "DISCOUNT:", "SHIPPING:", "TAX:",
            "TOTAL:", "NOTES:", "TERMS:", "CURRENCY:", "CURRENCY", "COMMERCIAL INVOICE",
            "INVOICE DATE", "INVOICE NUMBER", "DUE DATE",
            "TERMS", "STATUS", "CUSTOMER", "VENDOR", "DESCRIPTION", "AMOUNT", "S.NO.", "S.NO",
            "INVOICE #", "INVOICE #:",
        )

        if (
            "@" in candidate
            or ":" in candidate
            or re.search(r"\d", candidate)
            or len(candidate) <= 2
            or upper_candidate in excluded_labels
            or upper_candidate in ("QL",)
        ):
            return False

        return True

    if invoice_line_index is not None:

        # First, look AFTER the invoice heading.
        # This supports Northwind and SuperStore layouts.
        for candidate in lines[invoice_line_index + 1:invoice_line_index + 4]:
            if is_vendor_candidate(candidate):
                fields["Vendor"] = candidate
                break

        # If no vendor was found after the invoice heading,
        # look BEFORE it (for layouts such as Quantum Leaf).
        if fields["Vendor"] is None:
            for candidate in reversed(lines[:invoice_line_index]):
                if is_vendor_candidate(candidate):
                    fields["Vendor"] = candidate
                    break

    # Date: recognize common US formats and ISO dates.
    date_match = re.search(
        r"\b("
        r"\d{4}-\d{1,2}-\d{1,2}"
        r"|"
        r"\d{1,2}/\d{1,2}/\d{2,4}"
        r"|"
        r"[A-Za-z]{3,9}\s+\d{1,2},?\s+\d{4}"
        r"|"
        r"\d{1,2}\s+[A-Za-z]{3,9}\s+\d{4}"
        r")\b",
        text
    )

    if date_match:
        fields["Date"] = date_match.group(1)

    # Monetary amounts: recognize amounts after labels,
    # including amounts on the following line.
    for label in ("Subtotal", "Discount", "Shipping"):
        pattern = (
            rf"\b{label}\b"
            rf"\s*(?:\([^)]*\))?"
            rf"\s*:?\s*(?:USD\s*)?\$?\s*"
            rf"([\d,]+\.\d{{2}})"
        )

        amount_match = re.search(pattern, text, re.IGNORECASE)

        if amount_match:
            fields[label] = amount_match.group(1)

    # Recognize Promo labels as Discount.
    # Example: PROMO-SAVE10 -$57.00

    if fields["Discount"] is None:
        promo_pattern = (
            r"\bPROMO(?:[-\s][A-Z0-9]+)*"
            r"\s*:?\s*-?\s*\$?\s*"
            r"([\d,]+\.\d{2})"
        )

        promo_match = re.search(
            promo_pattern,
            text,
            re.IGNORECASE
        )

        if promo_match:
            fields["Discount"] = promo_match.group(1)

    # Recognize alternative labels for Shipping.
    if fields["Shipping"] is None:
        shipping_alternative_pattern = (
            r"\b(?:Delivery\s+Charge|Delivery\s+Fee|Freight|Shipping\s*&\s*Handling)\b"
            r"\s*:?\s*(?:USD\s*)?\$?\s*"
            r"([\d,]+\.\d{2})"
        )

        shipping_match = re.search(
            shipping_alternative_pattern,
            text,
            re.IGNORECASE
        )

        if shipping_match:
            fields["Shipping"] = shipping_match.group(1)


    # SuperStore layout: amounts appear BEFORE their labels.
    # Recognize three amounts followed by Subtotal, Shipping, and Total.

    summary_pattern = (
        r"(\$?[\d,]+\.\d{2})\s+"
        r"(\$?[\d,]+\.\d{2})\s+"
        r"(\$?[\d,]+\.\d{2})\s+"
        r"Subtotal\s*:?\s+"
        r"Shipping\s*:?\s+"
        r"Total\s*:?"
    )

    summary_match = re.search(
        summary_pattern,
        text,
        re.IGNORECASE
    )

    if summary_match:
        if fields["Subtotal"] is None:
            fields["Subtotal"] = summary_match.group(1).replace("$", "")

        if fields["Shipping"] is None:
            fields["Shipping"] = summary_match.group(2).replace("$", "")

        if fields["Total"] is None:
            fields["Total"] = summary_match.group(3).replace("$", "")

    
    # Tax: recognize Tax, Sales Tax, and GST labels.
    # Supports variable percentages using pct, percent, or %.

    tax_pattern = (
        r"\b(?:Sales\s+)?(?:Tax|GST)\b"
        r"\s*(?:\(?\s*\d+(?:\.\d+)?\s*(?:pct|percent|%)\s*\)?)?"
        r"\s*:?\s*(?:USD\s*)?\$?\s*"
        r"([\d,]+\.\d{2})"
    )

    tax_match = re.search(
        tax_pattern,
        text,
        re.IGNORECASE
    )

    if tax_match:
        fields["Tax"] = tax_match.group(1)

    # Total: recognize Total, Total Due, and similar labels.
    total_pattern = (
        r"\bTOTAL(?:\s+DUE)?\b"
        r"\s*:?\s*(?:USD\s*)?\$?\s*"
        r"([\d,]+\.\d{2})"
    )

    total_match = re.search(
        total_pattern,
        text,
        re.IGNORECASE
    )

    if total_match:
        fields["Total"] = total_match.group(1)

    return fields


def validate_invoice_total(fields):
    """Check whether known invoice amounts explain the total."""

    def to_number(value):
        if value is None:
            return None

        try:
            return float(value.replace(",", ""))
        except (ValueError, AttributeError):
            return None

    subtotal = to_number(fields.get("Subtotal"))
    discount = to_number(fields.get("Discount"))
    shipping = to_number(fields.get("Shipping"))
    tax = to_number(fields.get("Tax"))
    total = to_number(fields.get("Total"))

    if subtotal is None or total is None:
        return (
            "Needs review: subtotal or total is missing, "
            "so the calculation cannot be checked."
        )

    # Do not assume a missing discount or shipping charge is zero.
    # A missing value is treated as zero only when it is not present
    # in the invoice layout; we'll improve this distinction later.
    expected_total = subtotal

    if discount is not None:
        expected_total -= discount

    if shipping is not None:
        expected_total += shipping

    if tax is not None:
        expected_total += tax

    difference = round(total - expected_total, 2)

    if abs(difference) <= 0.02:
        return (
            "Calculation matches the extracted amounts. "
            "No separate tax amount was identified."
            if tax is None
            else "Calculation matches the extracted amounts."
        )

    return (
        f"Needs review: the total differs from the calculated "
        f"amount by ${difference:,.2f}. Check for missing charges, "
        "taxes, discounts, or extraction errors."
    )


# Page settings
st.set_page_config(
    page_title="K&B Solutions | Invoice Extractor",
    page_icon="🧾",
    layout="wide"
)
# Page navigation
if "current_page" not in st.session_state:
    st.session_state["current_page"] = "Upload Invoices"

if "all_invoice_results" not in st.session_state:
    st.session_state["all_invoice_results"] = []

# Company and application heading
st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@500;600;700&display=swap');
   
    .kb-brand {
        font-family: 'DM Sans', sans-serif;
        display: flex;
        align-items: center;
        gap: 12px;
        color: #123B5D;
        margin-bottom: 7px;
    }

    .kb-main {
        font-size: 60px;
        font-weight: 700;
        letter-spacing: -2px;
    }

    .kb-divider {
        font-size: 50px;
        font-weight: 400;
        color: #2878A8;
        line-height: 1;
        display: flex;
        align-items: center;
    }

    .kb-solutions {
        font-size: 40px;
        font-weight: 500;
        letter-spacing: 2px;
    }

    .block-container {
        padding-top: 3.5rem !important;
    }
    </style>

    <div class="kb-brand">
        <span class="kb-main">K&B</span>
        <span class="kb-divider">|</span>
        <span class="kb-solutions">Solutions</span>
    </div>

    <div style="display: flex; flex-direction: column; gap: 4px; margin-bottom: 12px;">
        <div style="height: 4px; background-color: #123B5D; width: 100%;"></div>
        <div style="height: 3px; background-color: #2878A8; width: 100%;"></div>
        <div style="height: 2px; background-color: #8FC5DF; width: 100%;"></div>
    </div>

    <div style="color: #526477; font-size: 15px; letter-spacing: 2px; font-weight: 600;">
        INVOICE EXTRACTOR
    </div>
    """,
    unsafe_allow_html=True
)

st.divider()

# Page navigation bar
page_col1, page_col2 = st.columns(2)

with page_col1:
    if st.button(
        "1. Upload Invoices",
        use_container_width=True,
        type="primary" if st.session_state["current_page"] == "Upload Invoices" else "secondary"
    ):
        st.session_state["current_page"] = "Upload Invoices"
        st.rerun()

with page_col2:
    if st.button(
        "2. Results",
        use_container_width=True,
        type="primary" if st.session_state["current_page"] == "Results" else "secondary"
    ):
        st.session_state["current_page"] = "Results"
        st.rerun()

st.divider()

# UPLOAD PAGE
if st.session_state["current_page"] == "Upload Invoices":

    # Introduction section
    st.markdown(
        """
        <div style="margin-top: -20px;">
            <h2 style="
                color: #123B5D;
                font-size: 35px;
                font-weight: 700;
                margin: 0 0 6px 0;
                padding: 0;
            ">
                Extract Invoice Information
            </h2>
            <p style="
                color: #526477;
                font-size: 20px;
                margin: 0 0 24px 0;
                padding: 0;
            ">
                Upload your PDF invoices to organize key invoice information
                in one easy-to-review table.
            </p>
        </div>
        """,
        unsafe_allow_html=True
    )

    # Instructions for users
    st.markdown(
        """
    <div style="
        background-color: #FFFFFF;
        border: 2px solid #2878A8;
        border-radius: 10px;
        padding: 12px 20px;
        margin: 10px 0 16px 0;
        color: #526477;
        font-size: 20px;
        line-height: 1.9;
    ">
        <h3 style="
            display: flex;
            align-items: center;
            gap: 9px;
            color: #123B5D;
            font-size: 28px;
            font-weight: 700;
            margin: 0 0 4px 0;
        ">
            <span style="
                display: inline-flex;
                align-items: center;
                justify-content: center;
                width: 25px;
                height: 25px;
                border-radius: 50%;
                background-color: #2878A8;
                color: #FFFFFF;
                font-size: 15px;
                font-weight: 700;
            ">i</span>
            Before You Upload
        </h3>
        <div style="padding-left: 34px;">
            <p style="margin: 0 0 6px 0;">• Upload PDF files only.</p>
            <p style="margin: 0 0 6px 0;">• Upload up to 20 invoices per batch.</p>
            <p style="margin: 0 0 6px 0;">• Invoices must contain readable text.</p>
            <p style="margin: 0;">• Extracted information will be available for review, including warnings for missing or unclear values.</p>
        </div>
    </div>
    """,
        unsafe_allow_html=True
    )

    # PDF upload area

    st.markdown(
        """
        <h3 style="
            color: #123B5D;
            font-size: 34px;
            font-weight: 700;
            margin: 10px 0 5px 0;
        ">Upload Your Invoices</h3>
        """,
        unsafe_allow_html=True
    )

    # Style the actual Streamlit upload box
    st.markdown(
        """
        <style>
        /* Main upload box */
        [data-testid="stFileUploader"] section {
            background-color: #DCECF5;
            border: 2px solid #123B5D;
            border-radius: 12px;
            padding: 6px 20px;
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            text-align: center;
        }

        /* Hide built-in upload button and instructions */
        [data-testid="stFileUploader"] section button,
        [data-testid="stFileUploader"] section small {
            display: none !important;
        }

        /* Remove positioning from internal elements */
        [data-testid="stFileUploader"] section > div {
            width: 100%;
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            text-align: center;
        }

        /* Cloud icon */
        [data-testid="stFileUploader"] section::before {
            content: "☁";
            display: block;
            color: #2878A8;
            font-size: 60px;
            text-align: center;
            width: 100%;
            margin-bottom: 0px;
        }

        /* Upload instructions */
        [data-testid="stFileUploader"] section::after {
            content: "Choose one or more invoices\A Select up to 20 files + maximum file size 200 MB per file.";
            display: block;
            white-space: pre-line;
            color: #123B5D;
            font-family: "DM Sans", "Trebuchet MS", sans-serif;
            font-size: 18px;
            font-weight: 500;
            line-height: 1.8;
            text-align: center;
            width: 100%;
            margin-top: 0px;
        }
        /* Reduce empty space inside uploader */
        [data-testid="stFileUploader"] section {
            gap: 0px !important;
            min-height: 0px !important;
        }

        /* Remove extra space around internal uploader elements */
        [data-testid="stFileUploader"] section > div {
            margin: 0px !important;
            padding: 0px !important;
            min-height: 0px !important;
        }

        /* Tighten space around the cloud */
        [data-testid="stFileUploader"] section::before {
            margin-bottom: 0px !important;
        }

        /* Tighten space around the instructions */
        [data-testid="stFileUploader"] section::after {
            margin-top: 0px !important;
        }
        
        /* Extract Invoices button styling */
        .st-key-extract_invoices button {
            background-color: #123B5D !important;
            color: #FFFFFF !important;
            border: 2px solid #123B5D !important;
            width: 100% !important;
            min-height: 58px !important;
            font-size: 18px !important;
            font-weight: 700 !important;
            border-radius: 8px !important;
        }

        .st-key-extract_invoices button:hover {
            background-color: #2878A8 !important;
            border-color: #2878A8 !important;
            color: #FFFFFF !important;
        }
        </style>
        """,
        unsafe_allow_html=True
    )

    uploaded_files = st.file_uploader(
        "",
        type=["pdf"],
        accept_multiple_files=True,
        label_visibility="collapsed",
    )

    # Show selected files
    if uploaded_files:
        if len(uploaded_files) > 20:
            st.error(
                "You selected more than 20 files. "
                "Please upload no more than 20 invoices at a time."
            )
        else:
            st.info(
                f"{len(uploaded_files)} invoices selected and ready to process."
            )


            if st.button(
                "Extract Invoices",
                use_container_width=True,
                type="primary",
                key="extract_invoices"
            ):
                all_invoice_results = []
                import fitz

                for uploaded_file in uploaded_files:
                    st.divider()
                    st.subheader(f"Testing: {uploaded_file.name}")

                    try:
                        pdf_bytes = uploaded_file.getvalue()

                        with fitz.open(
                            stream=pdf_bytes,
                            filetype="pdf"
                        ) as pdf_document:

                            # Extract all pages for the technical details section
                            extracted_text = "\n".join(
                                page.get_text()
                                for page in pdf_document
                            )

                            # Use only the first page to identify invoice details
                            first_page_text = pdf_document[0].get_text()
                            # TEMPORARY: Display extracted text for troubleshooting
                            with st.expander("View Extracted PDF Text"):
                                st.text(extracted_text)

                        if extracted_text.strip():
                            st.success("PDF text read successfully!")

                            
                            fields = extract_invoice_fields(extracted_text)
                            validation_message = validate_invoice_total(fields)

                            # Identify fields that still need review
                            missing_fields = [
                                field_name
                                for field_name, value in fields.items()
                                if value is None
                            ]

                            review_status = (
                                "Needs Review: " + ", ".join(missing_fields)
                                if missing_fields
                                else "Ready for Review"
                            )

                            # Display missing values clearly in the combined table
                            display_fields = {
                                field_name: value if value is not None else "Needs review"
                                for field_name, value in fields.items()
                            }

                            all_invoice_results.append({
                                "Source PDF": uploaded_file.name,
                                **display_fields,
                                "Review Status": review_status,
                                "Calculation Check": validation_message,
                            })

                        
                            st.subheader("Total Calculation Check")
                            st.info(validation_message)

                        
                            with st.expander("Technical Details — View Extracted PDF Text"):
                                st.text_area(
                                    "Raw PDF text",
                                    extracted_text,
                                    height=200,
                                    key=f"raw_text_{uploaded_file.name}",
                                )

                        else:
                            st.warning(
                                "No readable text was found. "
                                "This may be a scanned or image-only PDF."
                            )

                    except Exception as error:
                        st.error(
                            f"Could not read this PDF: {error}"
                        )

                st.session_state["all_invoice_results"] = all_invoice_results
                st.session_state["debug_invoice_text"] = extracted_text
                st.session_state["current_page"] = "Results"
                st.rerun()                          

    else:
        st.caption("No invoices selected yet.")


# RESULTS PAGE
if st.session_state["current_page"] == "Results":
    # Display saved invoice results outside the Test PDF button
    if st.session_state.get("all_invoice_results"):
        st.divider()
        st.header("Combined Invoice Results")

        results_df = pd.DataFrame(
            st.session_state["all_invoice_results"]
        )

        st.write("### Edit Extracted Invoice Information")

        # TEMPORARY: Display extracted PDF text for troubleshooting
        if st.session_state.get("debug_invoice_text"):
            with st.expander("View Extracted PDF Text"):
                st.text(st.session_state["debug_invoice_text"])

        edited_df = st.data_editor(
            results_df,
            use_container_width=True,
            hide_index=True,
            disabled=[
                "Source PDF",
                "Review Status",
                "Calculation Check"
            ],
            num_rows="fixed",
            key="invoice_editor"
        )

        st.caption(
            "Review flagged fields before relying on extracted values."
        )