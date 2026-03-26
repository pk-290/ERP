# ERP Sample Data Source Documentation

This document provides a comprehensive overview of the ERP sample data structure, mapping entities and their relationships across 19 datasets. All files are in `.jsonl` format.

## Overview of Entities

The data is organized into several functional areas:
1. **Business Partners & Customers**: Global master data for partners and their specific assignments.
2. **Products & Plants**: Material master data, descriptions, and plant-specific configurations.
3. **Sales Orders**: The entry point of the transactional flow.
4. **Outbound Deliveries**: Fulfillment records linked to sales orders.
5. **Billing Documents**: Invoices and cancellations linked to deliveries/sales orders.
6. **Accounting & Payments**: Financial records and settlement of accounts receivable.

---

## 1. Business Partners & Customers

### [business_partners](file:///Users/prathameshk/0xWT/ERP/sample_data/business_partners)
- **Primary Key**: `businessPartner`
- **Key Fields**: `customer` (maps to `soldToParty`), `businessPartnerFullName`, `businessPartnerGrouping`.
- **Note**: Core master record for any entity (Customer/Supplier).

### [business_partner_addresses](file:///Users/prathameshk/0xWT/ERP/sample_data/business_partner_addresses)
- **Link**: `businessPartner`
- **Key Fields**: `cityName`, `region`, `country`, `postalCode`.

### [customer_company_assignments](file:///Users/prathameshk/0xWT/ERP/sample_data/customer_company_assignments)
- **Link**: `customer`, `companyCode`
- **Key Fields**: `reconciliationAccount`, `paymentTerms`.

### [customer_sales_area_assignments](file:///Users/prathameshk/0xWT/ERP/sample_data/customer_sales_area_assignments)
- **Link**: `customer`, `salesOrganization`, `distributionChannel`, `division`
- **Key Fields**: `currency`, `shippingCondition`.

---

## 2. Products & Plants

### [products](file:///Users/prathameshk/0xWT/ERP/sample_data/products)
- **Primary Key**: `product`
- **Key Fields**: `productType`, `productGroup`, `baseUnit`, `netWeight`, `weightUnit`.

### [product_descriptions](file:///Users/prathameshk/0xWT/ERP/sample_data/product_descriptions)
- **Link**: `product`
- **Key Fields**: `language` (e.g., 'EN'), `productDescription`.

### [plants](file:///Users/prathameshk/0xWT/ERP/sample_data/plants)
- **Primary Key**: `plant`
- **Key Fields**: `plantName`, `salesOrganization`, `factoryCalendar`.

### [product_plants](file:///Users/prathameshk/0xWT/ERP/sample_data/product_plants)
- **Link**: `product`, `plant`
- **Key Fields**: `profitCenter`, `mrpType`, `availabilityCheckType`.

### [product_storage_locations](file:///Users/prathameshk/0xWT/ERP/sample_data/product_storage_locations)
- **Link**: `product`, `plant`
- **Key Fields**: `storageLocation`.

---

## 3. Sales Process (Order -> Delivery -> Billing)

### [sales_order_headers](file:///Users/prathameshk/0xWT/ERP/sample_data/sales_order_headers)
- **Primary Key**: `salesOrder`
- **Key Fields**: `soldToParty` (FK to `customer`), `totalNetAmount`, `overallDeliveryStatus`, `requestedDeliveryDate`.

### [sales_order_items](file:///Users/prathameshk/0xWT/ERP/sample_data/sales_order_items)
- **Primary Key**: `salesOrder` + `salesOrderItem`
- **Key Fields**: `material` (FK to `product`), `requestedQuantity`, `netAmount`, `productionPlant`.

### [sales_order_schedule_lines](file:///Users/prathameshk/0xWT/ERP/sample_data/sales_order_schedule_lines)
- **Link**: `salesOrder`, `salesOrderItem`
- **Key Fields**: `confirmedDeliveryDate`, `confdOrderQtyByMatlAvailCheck`.

---

### [outbound_delivery_headers](file:///Users/prathameshk/0xWT/ERP/sample_data/outbound_delivery_headers)
- **Primary Key**: `deliveryDocument`
- **Key Fields**: `shippingPoint`, `overallGoodsMovementStatus`, `deliveryDate`.

### [outbound_delivery_items](file:///Users/prathameshk/0xWT/ERP/sample_data/outbound_delivery_items)
- **Link**: `deliveryDocument`, `deliveryDocumentItem`
- **Key Fields**: `referenceSdDocument` (FK to `salesOrder`), `actualDeliveryQuantity`.

---

### [billing_document_headers](file:///Users/prathameshk/0xWT/ERP/sample_data/billing_document_headers)
- **Primary Key**: `billingDocument`
- **Key Fields**: `billingDocumentType`, `soldToParty`, `totalNetAmount`, `billingDocumentIsCancelled`.

### [billing_document_items](file:///Users/prathameshk/0xWT/ERP/sample_data/billing_document_items)
- **Link**: `billingDocument`, `billingDocumentItem`
- **Key Fields**: `material`, `billingQuantity`, `netAmount`, `referenceSdDocument` (FK to `deliveryDocument` or `salesOrder`).

### [billing_document_cancellations](file:///Users/prathameshk/0xWT/ERP/sample_data/billing_document_cancellations)
- **Link**: `billingDocument`
- **Key Fields**: `cancelledBillingDocument` (links the cancellation to the original doc).

---

## 4. Finance & Payments

### [journal_entry_items_accounts_receivable](file:///Users/prathameshk/0xWT/ERP/sample_data/journal_entry_items_accounts_receivable)
- **Link**: `accountingDocument`, `customer`
- **Key Fields**: `billingDocument` (direct link to invoice), `amountInTransactionCurrency`, `clearingAccountingDocument` (if paid).

### [payments_accounts_receivable](file:///Users/prathameshk/0xWT/ERP/sample_data/payments_accounts_receivable)
- **Link**: `accountingDocument` (the original invoice), `clearingAccountingDocument` (the payment doc)
- **Key Fields**: `clearingDate`, `amountInTransactionCurrency`.

---

## Relationship Summary (Data Flow)

1.  **Sales**: `sales_order_headers` -> `sales_order_items`
2.  **Fulfillment**: `outbound_delivery_headers` -> `outbound_delivery_items` (links to `salesOrder`)
3.  **Invoicing**: `billing_document_headers` -> `billing_document_items` (links to `deliveryDocument`)
4.  **Accounting**: `journal_entry_items_accounts_receivable` (links to `billingDocument`)
5.  **Payment**: `payments_accounts_receivable` (links `accountingDocument` to `clearingAccountingDocument`)
