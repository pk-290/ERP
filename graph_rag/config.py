"""
Configuration for graph RAG preprocessing pipeline.
Central place for all paths, node schemas, edge definitions, and field mappings.
"""
from pathlib import Path

# ─── Paths ───────────────────────────────────────────────────────────────────
DATA_DIR = Path(__file__).resolve().parent.parent / "sample_data"
OUTPUT_DIR = Path(__file__).resolve().parent / "output"

# ─── Node Type Constants ─────────────────────────────────────────────────────
CUSTOMER = "Customer"
PRODUCT = "Product"
PLANT = "Plant"
SALES_ORDER = "SalesOrder"
DELIVERY = "Delivery"
BILLING_DOC = "BillingDocument"
JOURNAL_ENTRY = "JournalEntry"

# ─── Edge Type Constants ─────────────────────────────────────────────────────
PLACED_ORDER = "PLACED_ORDER"
ORDER_CONTAINS = "ORDER_CONTAINS"
ORDER_FULFILLED_AT = "ORDER_FULFILLED_AT"
DELIVERED_BY = "DELIVERED_BY"
DELIVERY_CONTAINS = "DELIVERY_CONTAINS"
INVOICED_BY = "INVOICED_BY"
POSTED_AS = "POSTED_AS"
CLEARED_BY = "CLEARED_BY"
AVAILABLE_AT = "AVAILABLE_AT"
CANCELS = "CANCELS"
CUSTOMER_BILLED = "CUSTOMER_BILLED"  # Direct: Customer → BillingDocument (via soldToParty on billing header)

# ─── Node Schema Definitions ────────────────────────────────────────────────
# Maps raw JSONL field names → clean property names for each node type.
# Fields listed here are KEPT; everything else is stored in _raw.

CUSTOMER_FIELDS = {
    # From business_partners
    "businessPartner": "id",
    "businessPartnerFullName": "name",
    "businessPartnerCategory": "category",
    "businessPartnerGrouping": "grouping",
    "businessPartnerIsBlocked": "is_blocked",
    "isMarkedForArchiving": "is_archived",
    "creationDate": "created_date",
}

CUSTOMER_ADDRESS_FIELDS = {
    # From business_partner_addresses — merged into Customer node
    "cityName": "city",
    "region": "region",
    "country": "country",
    "postalCode": "postal_code",
    "streetName": "street",
    "addressTimeZone": "timezone",
}

CUSTOMER_COMPANY_FIELDS = {
    # From customer_company_assignments — merged into Customer node
    "reconciliationAccount": "reconciliation_account",
    "paymentTerms": "company_payment_terms",
    "customerAccountGroup": "account_group",
    "deletionIndicator": "is_deletion_flagged",
    "paymentBlockingReason": "payment_block_reason",
}

CUSTOMER_SALES_AREA_FIELDS = {
    # From customer_sales_area_assignments — merged into Customer node
    # NOTE: A customer can have MULTIPLE sales area assignments.
    # We store the first match as primary and collect all as a list in _sales_areas.
    "currency": "currency",
    "customerPaymentTerms": "payment_terms",
    "distributionChannel": "distribution_channel",
    "division": "division",
    "shippingCondition": "shipping_condition",
    "incotermsClassification": "incoterms",
    "incotermsLocation1": "incoterms_location",
    "deliveryPriority": "delivery_priority",
}

PRODUCT_FIELDS = {
    "product": "id",
    "productType": "type",
    "productGroup": "group",
    "baseUnit": "base_unit",
    "netWeight": "net_weight",
    "grossWeight": "gross_weight",
    "weightUnit": "weight_unit",
    "division": "division",
    "productOldId": "old_id",
    "isMarkedForDeletion": "is_deleted",
    "creationDate": "created_date",
    "industrySector": "industry_sector",
}

PLANT_FIELDS = {
    "plant": "id",
    "plantName": "name",
    "salesOrganization": "sales_organization",
    "factoryCalendar": "factory_calendar",
    "distributionChannel": "distribution_channel",
    "division": "division",
    "language": "language",
    "isMarkedForArchiving": "is_archived",
}

SALES_ORDER_FIELDS = {
    "salesOrder": "id",
    "salesOrderType": "type",
    "totalNetAmount": "total_net_amount",
    "transactionCurrency": "currency",
    "overallDeliveryStatus": "delivery_status",
    "requestedDeliveryDate": "requested_delivery_date",
    "creationDate": "creation_date",
    "pricingDate": "pricing_date",
    "customerPaymentTerms": "payment_terms",
    "incotermsClassification": "incoterms",
    "incotermsLocation1": "incoterms_location",
    "headerBillingBlockReason": "billing_block",
    "deliveryBlockReason": "delivery_block",
    "soldToParty": "_customer_id",  # underscore = FK, used for edge, not stored as property
    "distributionChannel": "distribution_channel",
    "organizationDivision": "division",
}

DELIVERY_FIELDS = {
    "deliveryDocument": "id",
    "shippingPoint": "shipping_point",
    "overallGoodsMovementStatus": "goods_movement_status",
    "overallPickingStatus": "picking_status",
    "creationDate": "creation_date",
    "actualGoodsMovementDate": "actual_goods_movement_date",
    "deliveryBlockReason": "delivery_block",
    "headerBillingBlockReason": "billing_block",
    "hdrGeneralIncompletionStatus": "incompletion_status",
}

BILLING_DOC_FIELDS = {
    "billingDocument": "id",
    "billingDocumentType": "type",
    "totalNetAmount": "total_net_amount",
    "transactionCurrency": "currency",
    "billingDocumentIsCancelled": "is_cancelled",
    "billingDocumentDate": "billing_date",
    "creationDate": "creation_date",
    "fiscalYear": "fiscal_year",
    "accountingDocument": "accounting_document",
    "companyCode": "company_code",
    "soldToParty": "_customer_id",
}

JOURNAL_ENTRY_FIELDS = {
    "accountingDocument": "id",
    "glAccount": "gl_account",
    "amountInTransactionCurrency": "amount",
    "transactionCurrency": "currency",
    "postingDate": "posting_date",
    "documentDate": "document_date",
    "accountingDocumentType": "document_type",
    "profitCenter": "profit_center",
    "clearingDate": "clearing_date",
    "clearingAccountingDocument": "clearing_document",
    "fiscalYear": "fiscal_year",
    "customer": "_customer_id",
    "referenceDocument": "_reference_document",
    "financialAccountType": "account_type",
    "costCenter": "cost_center",
}
