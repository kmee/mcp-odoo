"""
MCP server for Odoo integration

Provides MCP tools and resources for interacting with Odoo ERP systems
"""

import json
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, AsyncIterator, Dict, List, Optional, Union, cast

from mcp.server.fastmcp import Context, FastMCP
from pydantic import BaseModel, Field

from .odoo_client import OdooClient, get_odoo_client


@dataclass
class AppContext:
    """Application context for the MCP server"""

    odoo: OdooClient


@asynccontextmanager
async def app_lifespan(server: FastMCP) -> AsyncIterator[AppContext]:
    """
    Application lifespan for initialization and cleanup
    """
    # Initialize Odoo client on startup
    odoo_client = get_odoo_client()

    try:
        yield AppContext(odoo=odoo_client)
    finally:
        # No cleanup needed for Odoo client
        pass


# Create MCP server
mcp = FastMCP(
    name="Odoo MCP Server",
    instructions="MCP Server for interacting with Odoo ERP systems",
    lifespan=app_lifespan,
)


# ----- MCP Resources -----


@mcp.resource(
    "odoo://models", description="List all available models in the Odoo system"
)
def get_models() -> str:
    """Lists all available models in the Odoo system"""
    odoo_client = get_odoo_client()
    models = odoo_client.get_models()
    return json.dumps(models, indent=2)


@mcp.resource(
    "odoo://model/{model_name}",
    description="Get detailed information about a specific model including fields",
)
def get_model_info(model_name: str) -> str:
    """
    Get information about a specific model

    Parameters:
        model_name: Name of the Odoo model (e.g., 'res.partner')
    """
    odoo_client = get_odoo_client()
    try:
        # Get model info
        model_info = odoo_client.get_model_info(model_name)

        # Get field definitions
        fields = odoo_client.get_model_fields(model_name)
        model_info["fields"] = fields

        return json.dumps(model_info, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)}, indent=2)


@mcp.resource(
    "odoo://record/{model_name}/{record_id}",
    description="Get detailed information of a specific record by ID",
)
def get_record(model_name: str, record_id: str) -> str:
    """
    Get a specific record by ID

    Parameters:
        model_name: Name of the Odoo model (e.g., 'res.partner')
        record_id: ID of the record
    """
    odoo_client = get_odoo_client()
    try:
        record_id_int = int(record_id)
        record = odoo_client.read_records(model_name, [record_id_int])
        if not record:
            return json.dumps(
                {"error": f"Record not found: {model_name} ID {record_id}"}, indent=2
            )
        return json.dumps(record[0], indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)}, indent=2)


@mcp.resource(
    "odoo://search/{model_name}/{domain}",
    description="Search for records matching the domain",
)
def search_records_resource(model_name: str, domain: str) -> str:
    """
    Search for records that match a domain

    Parameters:
        model_name: Name of the Odoo model (e.g., 'res.partner')
        domain: Search domain in JSON format (e.g., '[["name", "ilike", "test"]]')
    """
    odoo_client = get_odoo_client()
    try:
        # Parse domain from JSON string
        domain_list = json.loads(domain)

        # Set a reasonable default limit
        limit = 10

        # Perform search_read for efficiency
        results = odoo_client.search_read(model_name, domain_list, limit=limit)

        return json.dumps(results, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)}, indent=2)


# ----- Pydantic models for type safety -----


class DomainCondition(BaseModel):
    """A single condition in a search domain"""

    field: str = Field(description="Field name to search")
    operator: str = Field(
        description="Operator (e.g., '=', '!=', '>', '<', 'in', 'not in', 'like', 'ilike')"
    )
    value: Any = Field(description="Value to compare against")

    def to_tuple(self) -> List:
        """Convert to Odoo domain condition tuple"""
        return [self.field, self.operator, self.value]


class SearchDomain(BaseModel):
    """Search domain for Odoo models"""

    conditions: List[DomainCondition] = Field(
        default_factory=list,
        description="List of conditions for searching. All conditions are combined with AND operator.",
    )

    def to_domain_list(self) -> List[List]:
        """Convert to Odoo domain list format"""
        return [condition.to_tuple() for condition in self.conditions]


class EmployeeSearchResult(BaseModel):
    """Represents a single employee search result."""

    id: int = Field(description="Employee ID")
    name: str = Field(description="Employee name")


class SearchEmployeeResponse(BaseModel):
    """Response model for the search_employee tool."""

    success: bool = Field(description="Indicates if the search was successful")
    result: Optional[List[EmployeeSearchResult]] = Field(
        default=None, description="List of employee search results"
    )
    error: Optional[str] = Field(default=None, description="Error message, if any")


class Holiday(BaseModel):
    """Represents a single holiday."""

    display_name: str = Field(description="Display name of the holiday")
    start_datetime: str = Field(description="Start date and time of the holiday")
    stop_datetime: str = Field(description="End date and time of the holiday")
    employee_id: List[Union[int, str]] = Field(
        description="Employee ID associated with the holiday"
    )
    name: str = Field(description="Name of the holiday")
    state: str = Field(description="State of the holiday")


class SearchHolidaysResponse(BaseModel):
    """Response model for the search_holidays tool."""

    success: bool = Field(description="Indicates if the search was successful")
    result: Optional[List[Holiday]] = Field(
        default=None, description="List of holidays found"
    )
    error: Optional[str] = Field(default=None, description="Error message, if any")


# ----- MCP Tools: CRUD Operations -----


@mcp.tool(description="Create a new record in an Odoo model")
def create_record(
    ctx: Context,
    model: str,
    values: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Create a new record in the specified Odoo model.

    Parameters:
        model: The model name (e.g., 'res.partner', 'sale.order')
        values: Dictionary of field values for the new record

    Returns:
        Dictionary containing:
        - success: Boolean indicating success
        - id: ID of the created record (if success)
        - error: Error message (if failure)

    Example:
        create_record("res.partner", {"name": "John Doe", "email": "john@example.com"})
    """
    odoo = ctx.request_context.lifespan_context.odoo
    try:
        record_id = odoo.execute_method(model, "create", values)
        return {"success": True, "id": record_id, "model": model}
    except Exception as e:
        return {"success": False, "error": str(e)}


@mcp.tool(description="Update existing records in an Odoo model")
def update_record(
    ctx: Context,
    model: str,
    ids: List[int],
    values: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Update existing records in the specified Odoo model.

    Parameters:
        model: The model name (e.g., 'res.partner')
        ids: List of record IDs to update
        values: Dictionary of field values to update

    Returns:
        Dictionary containing:
        - success: Boolean indicating success
        - updated_ids: List of updated record IDs
        - error: Error message (if failure)

    Example:
        update_record("res.partner", [1, 2], {"phone": "123456789"})
    """
    odoo = ctx.request_context.lifespan_context.odoo
    try:
        result = odoo.execute_method(model, "write", ids, values)
        return {"success": True, "updated_ids": ids, "result": result}
    except Exception as e:
        return {"success": False, "error": str(e)}


@mcp.tool(description="Delete records from an Odoo model")
def delete_record(
    ctx: Context,
    model: str,
    ids: List[int],
) -> Dict[str, Any]:
    """
    Delete records from the specified Odoo model.

    Parameters:
        model: The model name (e.g., 'res.partner')
        ids: List of record IDs to delete

    Returns:
        Dictionary containing:
        - success: Boolean indicating success
        - deleted_ids: List of deleted record IDs
        - error: Error message (if failure)

    Example:
        delete_record("res.partner", [5, 6])
    """
    odoo = ctx.request_context.lifespan_context.odoo
    try:
        result = odoo.execute_method(model, "unlink", ids)
        return {"success": True, "deleted_ids": ids, "result": result}
    except Exception as e:
        return {"success": False, "error": str(e)}


# ----- MCP Tools: Search Operations -----


@mcp.tool(description="Search for records in any Odoo model with pagination")
def search_records(
    ctx: Context,
    model: str,
    domain: List = None,
    fields: List[str] = None,
    offset: int = 0,
    limit: int = 80,
    order: str = None,
) -> Dict[str, Any]:
    """
    Search for records in any Odoo model with full pagination support.

    Parameters:
        model: The model name (e.g., 'res.partner', 'sale.order')
        domain: Search domain in Odoo format (e.g., [["is_company", "=", true]])
        fields: List of fields to return (None for default fields)
        offset: Number of records to skip (for pagination)
        limit: Maximum number of records to return (default 80)
        order: Sort order (e.g., "name asc, id desc")

    Returns:
        Dictionary containing:
        - success: Boolean indicating success
        - records: List of matching records
        - count: Total count of matching records
        - error: Error message (if failure)

    Examples:
        # Search all companies
        search_records("res.partner", [["is_company", "=", true]], limit=10)

        # Search products by name
        search_records("product.product", [["name", "ilike", "laptop"]], ["name", "list_price"])

        # Paginated search
        search_records("sale.order", [["state", "=", "sale"]], offset=20, limit=20)
    """
    odoo = ctx.request_context.lifespan_context.odoo
    try:
        domain = domain or []

        # Get total count
        count = odoo.execute_method(model, "search_count", domain)

        # Get records
        records = odoo.search_read(
            model_name=model,
            domain=domain,
            fields=fields,
            offset=offset,
            limit=limit,
            order=order,
        )

        return {
            "success": True,
            "records": records,
            "count": count,
            "offset": offset,
            "limit": limit,
            "has_more": (offset + len(records)) < count,
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


@mcp.tool(description="Count records matching a domain")
def count_records(
    ctx: Context,
    model: str,
    domain: List = None,
) -> Dict[str, Any]:
    """
    Count records matching a domain in an Odoo model.

    Parameters:
        model: The model name (e.g., 'res.partner')
        domain: Search domain in Odoo format

    Returns:
        Dictionary containing:
        - success: Boolean indicating success
        - count: Number of matching records
        - error: Error message (if failure)
    """
    odoo = ctx.request_context.lifespan_context.odoo
    try:
        domain = domain or []
        count = odoo.execute_method(model, "search_count", domain)
        return {"success": True, "count": count}
    except Exception as e:
        return {"success": False, "error": str(e)}


@mcp.tool(description="Read specific records by their IDs")
def read_records(
    ctx: Context,
    model: str,
    ids: List[int],
    fields: List[str] = None,
) -> Dict[str, Any]:
    """
    Read specific records by their IDs.

    Parameters:
        model: The model name (e.g., 'res.partner')
        ids: List of record IDs to read
        fields: List of fields to return (None for all fields)

    Returns:
        Dictionary containing:
        - success: Boolean indicating success
        - records: List of records
        - error: Error message (if failure)
    """
    odoo = ctx.request_context.lifespan_context.odoo
    try:
        records = odoo.read_records(model, ids, fields=fields)
        return {"success": True, "records": records}
    except Exception as e:
        return {"success": False, "error": str(e)}


# ----- MCP Tools: Model Introspection -----


@mcp.tool(description="Get detailed field information for a model")
def get_fields(
    ctx: Context,
    model: str,
    attributes: List[str] = None,
) -> Dict[str, Any]:
    """
    Get detailed field definitions for an Odoo model.

    Parameters:
        model: The model name (e.g., 'res.partner')
        attributes: List of field attributes to return (e.g., ['type', 'string', 'required'])
                   If None, returns all attributes.

    Returns:
        Dictionary containing:
        - success: Boolean indicating success
        - fields: Dictionary of field definitions
        - required_fields: List of required field names
        - error: Error message (if failure)

    Useful attributes:
        - type: Field type (char, integer, many2one, etc.)
        - string: Human-readable label
        - required: Whether the field is required
        - readonly: Whether the field is read-only
        - relation: Related model for relational fields
        - selection: Available options for selection fields
    """
    odoo = ctx.request_context.lifespan_context.odoo
    try:
        if attributes:
            fields = odoo.execute_method(model, "fields_get", [], {"attributes": attributes})
        else:
            fields = odoo.execute_method(model, "fields_get")

        # Extract required fields
        required_fields = [
            name for name, info in fields.items()
            if info.get("required", False) and not info.get("readonly", False)
        ]

        # Extract relational fields
        relational_fields = {
            name: info.get("relation")
            for name, info in fields.items()
            if info.get("relation")
        }

        return {
            "success": True,
            "fields": fields,
            "required_fields": required_fields,
            "relational_fields": relational_fields,
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


@mcp.tool(description="Get default values for creating a new record")
def get_default_values(
    ctx: Context,
    model: str,
    fields: List[str] = None,
) -> Dict[str, Any]:
    """
    Get default values for creating a new record.

    Parameters:
        model: The model name (e.g., 'sale.order')
        fields: List of fields to get defaults for (None for all)

    Returns:
        Dictionary containing:
        - success: Boolean indicating success
        - defaults: Dictionary of default values
        - error: Error message (if failure)
    """
    odoo = ctx.request_context.lifespan_context.odoo
    try:
        defaults = odoo.execute_method(model, "default_get", fields or [])
        return {"success": True, "defaults": defaults}
    except Exception as e:
        return {"success": False, "error": str(e)}


# ----- MCP Tools: Workflow Actions -----


@mcp.tool(description="Execute a workflow action on records")
def execute_action(
    ctx: Context,
    model: str,
    ids: List[int],
    action: str,
) -> Dict[str, Any]:
    """
    Execute a workflow action on records (e.g., confirm, cancel, done).

    Parameters:
        model: The model name (e.g., 'sale.order')
        ids: List of record IDs
        action: Action method name (e.g., 'action_confirm', 'action_cancel', 'action_done')

    Common actions by model:
        - sale.order: action_confirm, action_cancel, action_done
        - purchase.order: button_confirm, button_cancel
        - account.move: action_post, button_cancel, button_draft
        - stock.picking: action_confirm, action_assign, button_validate
        - mrp.production: action_confirm, action_assign, button_mark_done

    Returns:
        Dictionary containing:
        - success: Boolean indicating success
        - result: Result of the action
        - error: Error message (if failure)
    """
    odoo = ctx.request_context.lifespan_context.odoo
    try:
        result = odoo.execute_method(model, action, ids)
        return {"success": True, "result": result, "action": action, "ids": ids}
    except Exception as e:
        return {"success": False, "error": str(e)}


# ----- MCP Tools: Relationships -----


@mcp.tool(description="Get related records (many2one, one2many, many2many)")
def get_related_records(
    ctx: Context,
    model: str,
    ids: List[int],
    field: str,
    related_fields: List[str] = None,
    limit: int = 100,
) -> Dict[str, Any]:
    """
    Get related records for a relational field.

    Parameters:
        model: The source model name (e.g., 'sale.order')
        ids: List of record IDs from the source model
        field: Name of the relational field (e.g., 'order_line', 'partner_id')
        related_fields: Fields to read from related records
        limit: Maximum number of related records per source record

    Returns:
        Dictionary containing:
        - success: Boolean indicating success
        - records: Dictionary mapping source ID to related records
        - error: Error message (if failure)

    Example:
        # Get order lines for a sale order
        get_related_records("sale.order", [1], "order_line", ["product_id", "product_uom_qty", "price_unit"])
    """
    odoo = ctx.request_context.lifespan_context.odoo
    try:
        # First, get the field info to find the related model
        fields_info = odoo.execute_method(model, "fields_get", [field])
        if field not in fields_info:
            return {"success": False, "error": f"Field '{field}' not found in model '{model}'"}

        field_info = fields_info[field]
        field_type = field_info.get("type")
        relation = field_info.get("relation")

        if not relation:
            return {"success": False, "error": f"Field '{field}' is not a relational field"}

        # Read the source records to get related IDs
        source_records = odoo.read_records(model, ids, fields=[field])

        result = {}
        for record in source_records:
            record_id = record["id"]
            related_ids = record.get(field, [])

            if field_type == "many2one" and related_ids:
                # many2one returns [id, name] or False
                related_ids = [related_ids[0]] if isinstance(related_ids, list) else []
            elif not isinstance(related_ids, list):
                related_ids = []

            if related_ids:
                # Limit the related IDs
                related_ids = related_ids[:limit]
                related_records = odoo.read_records(relation, related_ids, fields=related_fields)
                result[record_id] = related_records
            else:
                result[record_id] = []

        return {
            "success": True,
            "records": result,
            "related_model": relation,
            "field_type": field_type,
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


# ----- MCP Tools: Common Models -----


@mcp.tool(description="Search partners/contacts with common filters")
def search_partners(
    ctx: Context,
    name: str = None,
    email: str = None,
    is_company: bool = None,
    customer_rank: bool = None,
    supplier_rank: bool = None,
    limit: int = 20,
) -> Dict[str, Any]:
    """
    Search for partners/contacts with common filters.

    Parameters:
        name: Filter by name (partial match)
        email: Filter by email (partial match)
        is_company: Filter by company/individual
        customer_rank: Filter for customers (customer_rank > 0)
        supplier_rank: Filter for suppliers (supplier_rank > 0)
        limit: Maximum number of records to return

    Returns:
        Dictionary containing:
        - success: Boolean indicating success
        - partners: List of partner records
        - count: Total matching count
        - error: Error message (if failure)
    """
    odoo = ctx.request_context.lifespan_context.odoo
    try:
        domain = []
        if name:
            domain.append(["name", "ilike", name])
        if email:
            domain.append(["email", "ilike", email])
        if is_company is not None:
            domain.append(["is_company", "=", is_company])
        if customer_rank:
            domain.append(["customer_rank", ">", 0])
        if supplier_rank:
            domain.append(["supplier_rank", ">", 0])

        count = odoo.execute_method("res.partner", "search_count", domain)
        partners = odoo.search_read(
            "res.partner",
            domain,
            fields=["id", "name", "email", "phone", "mobile", "is_company",
                    "street", "city", "country_id", "customer_rank", "supplier_rank"],
            limit=limit,
        )

        return {"success": True, "partners": partners, "count": count}
    except Exception as e:
        return {"success": False, "error": str(e)}


@mcp.tool(description="Search products with common filters")
def search_products(
    ctx: Context,
    name: str = None,
    default_code: str = None,
    categ_id: int = None,
    sale_ok: bool = None,
    purchase_ok: bool = None,
    type: str = None,
    limit: int = 20,
) -> Dict[str, Any]:
    """
    Search for products with common filters.

    Parameters:
        name: Filter by name (partial match)
        default_code: Filter by internal reference/SKU (partial match)
        categ_id: Filter by category ID
        sale_ok: Filter for saleable products
        purchase_ok: Filter for purchasable products
        type: Filter by product type ('consu', 'service', 'product')
        limit: Maximum number of records to return

    Returns:
        Dictionary containing:
        - success: Boolean indicating success
        - products: List of product records
        - count: Total matching count
        - error: Error message (if failure)
    """
    odoo = ctx.request_context.lifespan_context.odoo
    try:
        domain = []
        if name:
            domain.append(["name", "ilike", name])
        if default_code:
            domain.append(["default_code", "ilike", default_code])
        if categ_id:
            domain.append(["categ_id", "=", categ_id])
        if sale_ok is not None:
            domain.append(["sale_ok", "=", sale_ok])
        if purchase_ok is not None:
            domain.append(["purchase_ok", "=", purchase_ok])
        if type:
            domain.append(["type", "=", type])

        count = odoo.execute_method("product.product", "search_count", domain)
        products = odoo.search_read(
            "product.product",
            domain,
            fields=["id", "name", "default_code", "list_price", "standard_price",
                    "qty_available", "virtual_available", "categ_id", "type",
                    "sale_ok", "purchase_ok", "uom_id"],
            limit=limit,
        )

        return {"success": True, "products": products, "count": count}
    except Exception as e:
        return {"success": False, "error": str(e)}


@mcp.tool(description="Search sale orders with common filters")
def search_sale_orders(
    ctx: Context,
    name: str = None,
    partner_id: int = None,
    state: str = None,
    date_from: str = None,
    date_to: str = None,
    limit: int = 20,
) -> Dict[str, Any]:
    """
    Search for sale orders with common filters.

    Parameters:
        name: Filter by order reference (partial match)
        partner_id: Filter by customer ID
        state: Filter by state ('draft', 'sent', 'sale', 'done', 'cancel')
        date_from: Filter orders from this date (YYYY-MM-DD)
        date_to: Filter orders until this date (YYYY-MM-DD)
        limit: Maximum number of records to return

    Returns:
        Dictionary containing:
        - success: Boolean indicating success
        - orders: List of sale order records
        - count: Total matching count
        - error: Error message (if failure)
    """
    odoo = ctx.request_context.lifespan_context.odoo
    try:
        domain = []
        if name:
            domain.append(["name", "ilike", name])
        if partner_id:
            domain.append(["partner_id", "=", partner_id])
        if state:
            domain.append(["state", "=", state])
        if date_from:
            domain.append(["date_order", ">=", date_from])
        if date_to:
            domain.append(["date_order", "<=", date_to])

        count = odoo.execute_method("sale.order", "search_count", domain)
        orders = odoo.search_read(
            "sale.order",
            domain,
            fields=["id", "name", "partner_id", "date_order", "state",
                    "amount_untaxed", "amount_tax", "amount_total",
                    "user_id", "team_id", "invoice_status"],
            limit=limit,
            order="date_order desc",
        )

        return {"success": True, "orders": orders, "count": count}
    except Exception as e:
        return {"success": False, "error": str(e)}


@mcp.tool(description="Search invoices with common filters")
def search_invoices(
    ctx: Context,
    name: str = None,
    partner_id: int = None,
    state: str = None,
    move_type: str = None,
    date_from: str = None,
    date_to: str = None,
    limit: int = 20,
) -> Dict[str, Any]:
    """
    Search for invoices/bills with common filters.

    Parameters:
        name: Filter by invoice reference (partial match)
        partner_id: Filter by partner ID
        state: Filter by state ('draft', 'posted', 'cancel')
        move_type: Filter by type ('out_invoice', 'out_refund', 'in_invoice', 'in_refund')
        date_from: Filter invoices from this date (YYYY-MM-DD)
        date_to: Filter invoices until this date (YYYY-MM-DD)
        limit: Maximum number of records to return

    Returns:
        Dictionary containing:
        - success: Boolean indicating success
        - invoices: List of invoice records
        - count: Total matching count
        - error: Error message (if failure)
    """
    odoo = ctx.request_context.lifespan_context.odoo
    try:
        domain = [["move_type", "in", ["out_invoice", "out_refund", "in_invoice", "in_refund"]]]
        if name:
            domain.append(["name", "ilike", name])
        if partner_id:
            domain.append(["partner_id", "=", partner_id])
        if state:
            domain.append(["state", "=", state])
        if move_type:
            domain.append(["move_type", "=", move_type])
        if date_from:
            domain.append(["invoice_date", ">=", date_from])
        if date_to:
            domain.append(["invoice_date", "<=", date_to])

        count = odoo.execute_method("account.move", "search_count", domain)
        invoices = odoo.search_read(
            "account.move",
            domain,
            fields=["id", "name", "partner_id", "invoice_date", "invoice_date_due",
                    "state", "move_type", "amount_untaxed", "amount_tax", "amount_total",
                    "amount_residual", "payment_state"],
            limit=limit,
            order="invoice_date desc",
        )

        return {"success": True, "invoices": invoices, "count": count}
    except Exception as e:
        return {"success": False, "error": str(e)}


# ----- MCP Tools: Attachments -----


@mcp.tool(description="List attachments for a record")
def list_attachments(
    ctx: Context,
    model: str,
    res_id: int,
) -> Dict[str, Any]:
    """
    List all attachments for a specific record.

    Parameters:
        model: The model name (e.g., 'res.partner')
        res_id: The record ID

    Returns:
        Dictionary containing:
        - success: Boolean indicating success
        - attachments: List of attachment metadata
        - error: Error message (if failure)
    """
    odoo = ctx.request_context.lifespan_context.odoo
    try:
        attachments = odoo.search_read(
            "ir.attachment",
            [["res_model", "=", model], ["res_id", "=", res_id]],
            fields=["id", "name", "mimetype", "file_size", "create_date", "create_uid"],
        )
        return {"success": True, "attachments": attachments, "count": len(attachments)}
    except Exception as e:
        return {"success": False, "error": str(e)}


@mcp.tool(description="Create an attachment for a record")
def create_attachment(
    ctx: Context,
    name: str,
    model: str,
    res_id: int,
    data: str,
    mimetype: str = None,
) -> Dict[str, Any]:
    """
    Create an attachment for a specific record.

    Parameters:
        name: File name (e.g., 'document.pdf')
        model: The model name (e.g., 'res.partner')
        res_id: The record ID
        data: Base64 encoded file content
        mimetype: MIME type (e.g., 'application/pdf'). Auto-detected if not provided.

    Returns:
        Dictionary containing:
        - success: Boolean indicating success
        - attachment_id: ID of created attachment
        - error: Error message (if failure)
    """
    odoo = ctx.request_context.lifespan_context.odoo
    try:
        values = {
            "name": name,
            "res_model": model,
            "res_id": res_id,
            "datas": data,
            "type": "binary",
        }
        if mimetype:
            values["mimetype"] = mimetype

        attachment_id = odoo.execute_method("ir.attachment", "create", values)
        return {"success": True, "attachment_id": attachment_id}
    except Exception as e:
        return {"success": False, "error": str(e)}


@mcp.tool(description="Download/read an attachment content")
def read_attachment(
    ctx: Context,
    attachment_id: int,
) -> Dict[str, Any]:
    """
    Read the content of an attachment.

    Parameters:
        attachment_id: ID of the attachment

    Returns:
        Dictionary containing:
        - success: Boolean indicating success
        - name: File name
        - mimetype: MIME type
        - data: Base64 encoded file content
        - error: Error message (if failure)
    """
    odoo = ctx.request_context.lifespan_context.odoo
    try:
        attachment = odoo.read_records(
            "ir.attachment",
            [attachment_id],
            fields=["name", "mimetype", "datas"],
        )
        if not attachment:
            return {"success": False, "error": "Attachment not found"}

        return {
            "success": True,
            "name": attachment[0].get("name"),
            "mimetype": attachment[0].get("mimetype"),
            "data": attachment[0].get("datas"),
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


# ----- MCP Tools: Reports -----


@mcp.tool(description="Generate and download a PDF report")
def get_report_pdf(
    ctx: Context,
    report_name: str,
    ids: List[int],
) -> Dict[str, Any]:
    """
    Generate and download a PDF report for specific records.

    Parameters:
        report_name: Technical name of the report (e.g., 'sale.report_saleorder', 'account.report_invoice')
        ids: List of record IDs to include in the report

    Common report names:
        - sale.report_saleorder: Sale Order report
        - sale.report_saleorder_pro_forma: Pro-forma Invoice
        - account.report_invoice: Invoice report
        - account.report_invoice_with_payments: Invoice with payments
        - purchase.report_purchaseorder: Purchase Order
        - stock.report_picking: Picking/Delivery slip
        - stock.report_deliveryslip: Delivery slip

    Returns:
        Dictionary containing:
        - success: Boolean indicating success
        - data: Base64 encoded PDF content
        - filename: Suggested filename
        - error: Error message (if failure)
    """
    odoo = ctx.request_context.lifespan_context.odoo
    try:
        # Use render_qweb_pdf to generate the report
        result = odoo.execute_method(
            "ir.actions.report",
            "_render_qweb_pdf",
            report_name,
            ids,
        )

        if result and len(result) >= 2:
            import base64
            pdf_content = result[0]
            # result[0] is bytes, encode to base64
            pdf_base64 = base64.b64encode(pdf_content).decode("utf-8")
            return {
                "success": True,
                "data": pdf_base64,
                "filename": f"{report_name.split('.')[-1]}_{ids[0]}.pdf",
            }
        else:
            return {"success": False, "error": "Failed to generate report"}
    except Exception as e:
        return {"success": False, "error": str(e)}


# ----- MCP Tools: Company & Users -----


@mcp.tool(description="Get current user information")
def get_current_user(
    ctx: Context,
) -> Dict[str, Any]:
    """
    Get information about the currently authenticated user.

    Returns:
        Dictionary containing:
        - success: Boolean indicating success
        - user: User information
        - error: Error message (if failure)
    """
    odoo = ctx.request_context.lifespan_context.odoo
    try:
        user = odoo.read_records(
            "res.users",
            [odoo.uid],
            fields=["id", "name", "login", "email", "company_id", "company_ids",
                    "groups_id", "partner_id", "lang", "tz"],
        )
        if not user:
            return {"success": False, "error": "User not found"}

        return {"success": True, "user": user[0]}
    except Exception as e:
        return {"success": False, "error": str(e)}


@mcp.tool(description="Get company information")
def get_company_info(
    ctx: Context,
    company_id: int = None,
) -> Dict[str, Any]:
    """
    Get information about a company.

    Parameters:
        company_id: Company ID (None for current user's company)

    Returns:
        Dictionary containing:
        - success: Boolean indicating success
        - company: Company information
        - error: Error message (if failure)
    """
    odoo = ctx.request_context.lifespan_context.odoo
    try:
        if not company_id:
            # Get current user's company
            user = odoo.read_records("res.users", [odoo.uid], fields=["company_id"])
            if user and user[0].get("company_id"):
                company_id = user[0]["company_id"][0]
            else:
                return {"success": False, "error": "Could not determine company"}

        company = odoo.read_records(
            "res.company",
            [company_id],
            fields=["id", "name", "email", "phone", "website", "street", "city",
                    "state_id", "country_id", "zip", "vat", "currency_id"],
        )
        if not company:
            return {"success": False, "error": "Company not found"}

        return {"success": True, "company": company[0]}
    except Exception as e:
        return {"success": False, "error": str(e)}


# ----- MCP Tools: Messaging/Chatter -----


@mcp.tool(description="Post a public comment on a record (visible to customers)")
def post_comment(
    ctx: Context,
    model: str,
    res_id: int,
    body: str,
    partner_ids: List[int] = None,
    attachment_ids: List[int] = None,
) -> Dict[str, Any]:
    """
    Post a public comment on a record's chatter.
    Comments are visible to followers including external partners/customers.

    Parameters:
        model: The model name (e.g., 'sale.order', 'helpdesk.ticket')
        res_id: The record ID
        body: HTML content of the message (supports basic HTML tags)
        partner_ids: List of partner IDs to notify (optional)
        attachment_ids: List of attachment IDs to include (optional)

    Returns:
        Dictionary containing:
        - success: Boolean indicating success
        - message_id: ID of the created message
        - error: Error message (if failure)

    Example:
        post_comment("sale.order", 1, "<p>Your order has been shipped!</p>", partner_ids=[5])
    """
    odoo = ctx.request_context.lifespan_context.odoo
    try:
        kwargs = {
            "body": body,
            "message_type": "comment",
            "subtype_xmlid": "mail.mt_comment",
        }
        if partner_ids:
            kwargs["partner_ids"] = partner_ids
        if attachment_ids:
            kwargs["attachment_ids"] = attachment_ids

        message_id = odoo.execute_method(model, "message_post", [res_id], **kwargs)
        return {"success": True, "message_id": message_id}
    except Exception as e:
        return {"success": False, "error": str(e)}


@mcp.tool(description="Post an internal note on a record (not visible to customers)")
def post_internal_note(
    ctx: Context,
    model: str,
    res_id: int,
    body: str,
    partner_ids: List[int] = None,
    attachment_ids: List[int] = None,
) -> Dict[str, Any]:
    """
    Post an internal note on a record's chatter.
    Internal notes are only visible to internal users, NOT to external partners/customers.

    Parameters:
        model: The model name (e.g., 'sale.order', 'res.partner')
        res_id: The record ID
        body: HTML content of the note
        partner_ids: List of internal user partner IDs to notify (optional)
        attachment_ids: List of attachment IDs to include (optional)

    Returns:
        Dictionary containing:
        - success: Boolean indicating success
        - message_id: ID of the created message
        - error: Error message (if failure)

    Example:
        post_internal_note("sale.order", 1, "<p>Customer requested urgent delivery</p>")
    """
    odoo = ctx.request_context.lifespan_context.odoo
    try:
        kwargs = {
            "body": body,
            "message_type": "comment",
            "subtype_xmlid": "mail.mt_note",  # Internal note subtype
        }
        if partner_ids:
            kwargs["partner_ids"] = partner_ids
        if attachment_ids:
            kwargs["attachment_ids"] = attachment_ids

        message_id = odoo.execute_method(model, "message_post", [res_id], **kwargs)
        return {"success": True, "message_id": message_id}
    except Exception as e:
        return {"success": False, "error": str(e)}


@mcp.tool(description="Send an email from a record")
def send_email(
    ctx: Context,
    model: str,
    res_id: int,
    subject: str,
    body: str,
    partner_ids: List[int],
    attachment_ids: List[int] = None,
    email_from: str = None,
) -> Dict[str, Any]:
    """
    Send an email from a record's chatter.

    Parameters:
        model: The model name (e.g., 'sale.order')
        res_id: The record ID
        subject: Email subject
        body: HTML content of the email
        partner_ids: List of partner IDs to send the email to
        attachment_ids: List of attachment IDs to include (optional)
        email_from: Sender email address (optional, uses default if not provided)

    Returns:
        Dictionary containing:
        - success: Boolean indicating success
        - message_id: ID of the created message
        - error: Error message (if failure)
    """
    odoo = ctx.request_context.lifespan_context.odoo
    try:
        kwargs = {
            "body": body,
            "subject": subject,
            "message_type": "email",
            "subtype_xmlid": "mail.mt_comment",
            "partner_ids": partner_ids,
        }
        if attachment_ids:
            kwargs["attachment_ids"] = attachment_ids
        if email_from:
            kwargs["email_from"] = email_from

        message_id = odoo.execute_method(model, "message_post", [res_id], **kwargs)
        return {"success": True, "message_id": message_id}
    except Exception as e:
        return {"success": False, "error": str(e)}


@mcp.tool(description="Get messages/chatter history for a record with filters")
def get_messages(
    ctx: Context,
    model: str,
    res_id: int,
    message_type: str = None,
    include_internal: bool = True,
    limit: int = 50,
    offset: int = 0,
) -> Dict[str, Any]:
    """
    Get the message history (chatter) for a record with filtering options.

    Parameters:
        model: The model name (e.g., 'sale.order')
        res_id: The record ID
        message_type: Filter by message type ('comment', 'email', 'notification', None for all)
        include_internal: Whether to include internal notes (default True)
        limit: Maximum number of messages to return
        offset: Number of messages to skip (for pagination)

    Returns:
        Dictionary containing:
        - success: Boolean indicating success
        - messages: List of messages with details
        - count: Total number of messages
        - error: Error message (if failure)
    """
    odoo = ctx.request_context.lifespan_context.odoo
    try:
        domain = [["model", "=", model], ["res_id", "=", res_id]]

        if message_type:
            domain.append(["message_type", "=", message_type])

        if not include_internal:
            # Exclude internal notes by filtering out mail.mt_note subtype
            domain.append(["subtype_id.internal", "=", False])

        count = odoo.execute_method("mail.message", "search_count", domain)

        messages = odoo.search_read(
            "mail.message",
            domain,
            fields=[
                "id",
                "date",
                "author_id",
                "body",
                "message_type",
                "subtype_id",
                "subject",
                "partner_ids",
                "attachment_ids",
                "email_from",
                "starred",
            ],
            limit=limit,
            offset=offset,
            order="date desc",
        )
        return {
            "success": True,
            "messages": messages,
            "count": count,
            "has_more": (offset + len(messages)) < count,
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


# ----- MCP Tools: Followers -----


@mcp.tool(description="Get followers of a record")
def get_followers(
    ctx: Context,
    model: str,
    res_id: int,
) -> Dict[str, Any]:
    """
    Get all followers of a record.

    Parameters:
        model: The model name (e.g., 'sale.order')
        res_id: The record ID

    Returns:
        Dictionary containing:
        - success: Boolean indicating success
        - followers: List of followers with partner details
        - count: Number of followers
        - error: Error message (if failure)
    """
    odoo = ctx.request_context.lifespan_context.odoo
    try:
        followers = odoo.search_read(
            "mail.followers",
            [["res_model", "=", model], ["res_id", "=", res_id]],
            fields=["id", "partner_id", "subtype_ids"],
        )

        # Get partner details for each follower
        partner_ids = [f["partner_id"][0] for f in followers if f.get("partner_id")]
        partners = {}
        if partner_ids:
            partner_records = odoo.read_records(
                "res.partner",
                partner_ids,
                fields=["id", "name", "email", "is_company"],
            )
            partners = {p["id"]: p for p in partner_records}

        # Enrich followers with partner details
        for f in followers:
            if f.get("partner_id"):
                partner_id = f["partner_id"][0]
                f["partner_details"] = partners.get(partner_id, {})

        return {"success": True, "followers": followers, "count": len(followers)}
    except Exception as e:
        return {"success": False, "error": str(e)}


@mcp.tool(description="Add followers to a record")
def add_followers(
    ctx: Context,
    model: str,
    res_id: int,
    partner_ids: List[int],
    send_notification: bool = True,
) -> Dict[str, Any]:
    """
    Add followers to a record.

    Parameters:
        model: The model name (e.g., 'sale.order')
        res_id: The record ID
        partner_ids: List of partner IDs to add as followers
        send_notification: Whether to send a notification to new followers

    Returns:
        Dictionary containing:
        - success: Boolean indicating success
        - added_partners: List of added partner IDs
        - error: Error message (if failure)
    """
    odoo = ctx.request_context.lifespan_context.odoo
    try:
        if send_notification:
            odoo.execute_method(
                model,
                "message_subscribe",
                [res_id],
                partner_ids=partner_ids,
            )
        else:
            # Add followers without notification
            for partner_id in partner_ids:
                odoo.execute_method(
                    "mail.followers",
                    "create",
                    {
                        "res_model": model,
                        "res_id": res_id,
                        "partner_id": partner_id,
                    },
                )
        return {"success": True, "added_partners": partner_ids}
    except Exception as e:
        return {"success": False, "error": str(e)}


@mcp.tool(description="Remove followers from a record")
def remove_followers(
    ctx: Context,
    model: str,
    res_id: int,
    partner_ids: List[int],
) -> Dict[str, Any]:
    """
    Remove followers from a record.

    Parameters:
        model: The model name (e.g., 'sale.order')
        res_id: The record ID
        partner_ids: List of partner IDs to remove from followers

    Returns:
        Dictionary containing:
        - success: Boolean indicating success
        - removed_partners: List of removed partner IDs
        - error: Error message (if failure)
    """
    odoo = ctx.request_context.lifespan_context.odoo
    try:
        odoo.execute_method(
            model,
            "message_unsubscribe",
            [res_id],
            partner_ids=partner_ids,
        )
        return {"success": True, "removed_partners": partner_ids}
    except Exception as e:
        return {"success": False, "error": str(e)}


# ----- MCP Tools: Activities -----


@mcp.tool(description="Create a scheduled activity on a record")
def create_activity(
    ctx: Context,
    model: str,
    res_id: int,
    activity_type: str,
    summary: str,
    date_deadline: str,
    user_id: int = None,
    note: str = None,
) -> Dict[str, Any]:
    """
    Create a scheduled activity on a record (todo, meeting, call, email, etc.).

    Parameters:
        model: The model name (e.g., 'res.partner', 'sale.order')
        res_id: The record ID
        activity_type: Type of activity. Common types:
            - 'mail.mail_activity_data_todo': To-Do
            - 'mail.mail_activity_data_call': Call
            - 'mail.mail_activity_data_meeting': Meeting
            - 'mail.mail_activity_data_email': Email
            - 'mail.mail_activity_data_upload_document': Upload Document
        summary: Short summary/title of the activity
        date_deadline: Due date in YYYY-MM-DD format
        user_id: User ID to assign the activity to (None for current user)
        note: Detailed description/notes (HTML supported)

    Returns:
        Dictionary containing:
        - success: Boolean indicating success
        - activity_id: ID of the created activity
        - error: Error message (if failure)

    Example:
        create_activity(
            "res.partner", 1,
            "mail.mail_activity_data_call",
            "Follow up on proposal",
            "2024-01-20",
            note="<p>Discuss pricing options</p>"
        )
    """
    odoo = ctx.request_context.lifespan_context.odoo
    try:
        # Validate date format
        try:
            datetime.strptime(date_deadline, "%Y-%m-%d")
        except ValueError:
            return {"success": False, "error": "Invalid date_deadline format. Use YYYY-MM-DD"}

        # Get activity type ID from xmlid
        activity_type_id = None
        try:
            result = odoo.execute_method(
                "ir.model.data",
                "xmlid_to_res_id",
                activity_type,
            )
            activity_type_id = result
        except Exception:
            # Try to find by name if xmlid fails
            types = odoo.search_read(
                "mail.activity.type",
                [["name", "ilike", activity_type.split("_")[-1]]],
                fields=["id"],
                limit=1,
            )
            if types:
                activity_type_id = types[0]["id"]

        if not activity_type_id:
            return {"success": False, "error": f"Activity type '{activity_type}' not found"}

        values = {
            "res_model": model,
            "res_id": res_id,
            "activity_type_id": activity_type_id,
            "summary": summary,
            "date_deadline": date_deadline,
        }

        if user_id:
            values["user_id"] = user_id

        if note:
            values["note"] = note

        activity_id = odoo.execute_method("mail.activity", "create", values)
        return {"success": True, "activity_id": activity_id}
    except Exception as e:
        return {"success": False, "error": str(e)}


@mcp.tool(description="Get scheduled activities for a record or user")
def get_activities(
    ctx: Context,
    model: str = None,
    res_id: int = None,
    user_id: int = None,
    state: str = None,
    limit: int = 50,
) -> Dict[str, Any]:
    """
    Get scheduled activities with various filters.

    Parameters:
        model: Filter by model name (optional)
        res_id: Filter by record ID (requires model)
        user_id: Filter by assigned user ID (None for all users)
        state: Filter by state ('overdue', 'today', 'planned', None for all)
        limit: Maximum number of activities to return

    Returns:
        Dictionary containing:
        - success: Boolean indicating success
        - activities: List of activities with details
        - count: Total number of activities
        - error: Error message (if failure)
    """
    odoo = ctx.request_context.lifespan_context.odoo
    try:
        domain = []

        if model:
            domain.append(["res_model", "=", model])
        if res_id and model:
            domain.append(["res_id", "=", res_id])
        if user_id:
            domain.append(["user_id", "=", user_id])

        # Filter by state (deadline comparison)
        today = datetime.now().strftime("%Y-%m-%d")
        if state == "overdue":
            domain.append(["date_deadline", "<", today])
        elif state == "today":
            domain.append(["date_deadline", "=", today])
        elif state == "planned":
            domain.append(["date_deadline", ">", today])

        count = odoo.execute_method("mail.activity", "search_count", domain)

        activities = odoo.search_read(
            "mail.activity",
            domain,
            fields=[
                "id",
                "res_model",
                "res_id",
                "res_name",
                "activity_type_id",
                "summary",
                "note",
                "date_deadline",
                "user_id",
                "create_uid",
                "create_date",
                "state",
            ],
            limit=limit,
            order="date_deadline asc",
        )
        return {"success": True, "activities": activities, "count": count}
    except Exception as e:
        return {"success": False, "error": str(e)}


@mcp.tool(description="Get my pending activities")
def get_my_activities(
    ctx: Context,
    include_overdue: bool = True,
    include_today: bool = True,
    include_planned: bool = True,
    limit: int = 50,
) -> Dict[str, Any]:
    """
    Get activities assigned to the current user.

    Parameters:
        include_overdue: Include overdue activities
        include_today: Include activities due today
        include_planned: Include future activities
        limit: Maximum number of activities to return

    Returns:
        Dictionary containing:
        - success: Boolean indicating success
        - activities: List of activities grouped by state
        - summary: Count by state
        - error: Error message (if failure)
    """
    odoo = ctx.request_context.lifespan_context.odoo
    try:
        today = datetime.now().strftime("%Y-%m-%d")
        result = {"overdue": [], "today": [], "planned": []}
        summary = {"overdue": 0, "today": 0, "planned": 0}

        base_domain = [["user_id", "=", odoo.uid]]
        fields = [
            "id",
            "res_model",
            "res_id",
            "res_name",
            "activity_type_id",
            "summary",
            "date_deadline",
            "state",
        ]

        if include_overdue:
            domain = base_domain + [["date_deadline", "<", today]]
            result["overdue"] = odoo.search_read(
                "mail.activity", domain, fields=fields, limit=limit, order="date_deadline asc"
            )
            summary["overdue"] = odoo.execute_method("mail.activity", "search_count", domain)

        if include_today:
            domain = base_domain + [["date_deadline", "=", today]]
            result["today"] = odoo.search_read(
                "mail.activity", domain, fields=fields, limit=limit, order="date_deadline asc"
            )
            summary["today"] = odoo.execute_method("mail.activity", "search_count", domain)

        if include_planned:
            domain = base_domain + [["date_deadline", ">", today]]
            result["planned"] = odoo.search_read(
                "mail.activity", domain, fields=fields, limit=limit, order="date_deadline asc"
            )
            summary["planned"] = odoo.execute_method("mail.activity", "search_count", domain)

        return {"success": True, "activities": result, "summary": summary}
    except Exception as e:
        return {"success": False, "error": str(e)}


@mcp.tool(description="Mark an activity as done")
def complete_activity(
    ctx: Context,
    activity_id: int,
    feedback: str = None,
) -> Dict[str, Any]:
    """
    Mark an activity as done/completed.

    Parameters:
        activity_id: ID of the activity to complete
        feedback: Optional feedback message to log

    Returns:
        Dictionary containing:
        - success: Boolean indicating success
        - error: Error message (if failure)
    """
    odoo = ctx.request_context.lifespan_context.odoo
    try:
        if feedback:
            odoo.execute_method(
                "mail.activity",
                "action_feedback",
                [activity_id],
                feedback=feedback,
            )
        else:
            odoo.execute_method(
                "mail.activity",
                "action_done",
                [activity_id],
            )
        return {"success": True, "completed_activity_id": activity_id}
    except Exception as e:
        return {"success": False, "error": str(e)}


@mcp.tool(description="Cancel/delete an activity")
def cancel_activity(
    ctx: Context,
    activity_id: int,
) -> Dict[str, Any]:
    """
    Cancel/delete a scheduled activity.

    Parameters:
        activity_id: ID of the activity to cancel

    Returns:
        Dictionary containing:
        - success: Boolean indicating success
        - error: Error message (if failure)
    """
    odoo = ctx.request_context.lifespan_context.odoo
    try:
        odoo.execute_method("mail.activity", "unlink", [activity_id])
        return {"success": True, "cancelled_activity_id": activity_id}
    except Exception as e:
        return {"success": False, "error": str(e)}


@mcp.tool(description="Reschedule an activity to a new date")
def reschedule_activity(
    ctx: Context,
    activity_id: int,
    new_date: str,
    new_user_id: int = None,
) -> Dict[str, Any]:
    """
    Reschedule an activity to a new deadline date.

    Parameters:
        activity_id: ID of the activity to reschedule
        new_date: New deadline date in YYYY-MM-DD format
        new_user_id: Optionally reassign to a different user

    Returns:
        Dictionary containing:
        - success: Boolean indicating success
        - error: Error message (if failure)
    """
    odoo = ctx.request_context.lifespan_context.odoo
    try:
        # Validate date format
        try:
            datetime.strptime(new_date, "%Y-%m-%d")
        except ValueError:
            return {"success": False, "error": "Invalid new_date format. Use YYYY-MM-DD"}

        values = {"date_deadline": new_date}
        if new_user_id:
            values["user_id"] = new_user_id

        odoo.execute_method("mail.activity", "write", [activity_id], values)
        return {"success": True, "rescheduled_activity_id": activity_id, "new_date": new_date}
    except Exception as e:
        return {"success": False, "error": str(e)}


@mcp.tool(description="Get available activity types")
def get_activity_types(
    ctx: Context,
) -> Dict[str, Any]:
    """
    Get all available activity types in the system.

    Returns:
        Dictionary containing:
        - success: Boolean indicating success
        - activity_types: List of activity types with details
        - error: Error message (if failure)
    """
    odoo = ctx.request_context.lifespan_context.odoo
    try:
        activity_types = odoo.search_read(
            "mail.activity.type",
            [],
            fields=["id", "name", "summary", "icon", "decoration_type", "res_model", "delay_count", "delay_unit"],
            order="sequence asc",
        )
        return {"success": True, "activity_types": activity_types}
    except Exception as e:
        return {"success": False, "error": str(e)}


# ----- MCP Tools: Assignment & Delegation -----


@mcp.tool(description="Delegate an activity to another user")
def delegate_activity(
    ctx: Context,
    activity_id: int,
    user_id: int,
    note: str = None,
) -> Dict[str, Any]:
    """
    Delegate an activity to another user.

    Parameters:
        activity_id: ID of the activity to delegate
        user_id: ID of the user to delegate to
        note: Optional note explaining the delegation

    Returns:
        Dictionary containing:
        - success: Boolean indicating success
        - delegated_to: User ID the activity was delegated to
        - error: Error message (if failure)
    """
    odoo = ctx.request_context.lifespan_context.odoo
    try:
        # Update the activity's assigned user
        values = {"user_id": user_id}

        # If note provided, append to existing note
        if note:
            activity = odoo.read_records("mail.activity", [activity_id], fields=["note", "res_model", "res_id"])
            if activity:
                existing_note = activity[0].get("note") or ""
                delegation_note = f"<p><strong>Delegated:</strong> {note}</p>"
                values["note"] = existing_note + delegation_note

                # Also post a message about the delegation
                model = activity[0].get("res_model")
                res_id = activity[0].get("res_id")
                if model and res_id:
                    # Get user name
                    user = odoo.read_records("res.users", [user_id], fields=["name"])
                    user_name = user[0]["name"] if user else f"User {user_id}"
                    odoo.execute_method(
                        model,
                        "message_post",
                        [res_id],
                        body=f"<p>Activity delegated to <strong>{user_name}</strong>: {note}</p>",
                        message_type="comment",
                        subtype_xmlid="mail.mt_note",
                    )

        odoo.execute_method("mail.activity", "write", [activity_id], values)
        return {"success": True, "delegated_to": user_id, "activity_id": activity_id}
    except Exception as e:
        return {"success": False, "error": str(e)}


@mcp.tool(description="Assign a record to a user (set responsible)")
def assign_record(
    ctx: Context,
    model: str,
    res_id: int,
    user_id: int,
    user_field: str = "user_id",
    notify: bool = True,
) -> Dict[str, Any]:
    """
    Assign a record to a user by setting the responsible/assigned user field.

    Parameters:
        model: The model name (e.g., 'crm.lead', 'project.task', 'helpdesk.ticket')
        res_id: The record ID
        user_id: ID of the user to assign
        user_field: Name of the user field (default 'user_id', could be 'assigned_user_id', etc.)
        notify: Whether to notify the user about the assignment

    Returns:
        Dictionary containing:
        - success: Boolean indicating success
        - assigned_to: User ID the record was assigned to
        - error: Error message (if failure)

    Common user fields by model:
        - crm.lead: user_id
        - project.task: user_ids (many2many)
        - helpdesk.ticket: user_id
        - sale.order: user_id
        - hr.applicant: user_id
    """
    odoo = ctx.request_context.lifespan_context.odoo
    try:
        # Check if it's a many2many field
        fields_info = odoo.execute_method(model, "fields_get", [user_field])
        field_type = fields_info.get(user_field, {}).get("type")

        if field_type == "many2many":
            # For many2many, use special command to add user
            values = {user_field: [(4, user_id)]}  # (4, id) = link
        else:
            values = {user_field: user_id}

        odoo.execute_method(model, "write", [res_id], values)

        # Optionally notify the user
        if notify:
            user = odoo.read_records("res.users", [user_id], fields=["name", "partner_id"])
            if user and user[0].get("partner_id"):
                user_name = user[0]["name"]
                partner_id = user[0]["partner_id"][0]
                odoo.execute_method(
                    model,
                    "message_post",
                    [res_id],
                    body=f"<p>This record has been assigned to <strong>{user_name}</strong></p>",
                    message_type="comment",
                    subtype_xmlid="mail.mt_note",
                    partner_ids=[partner_id],
                )

        return {"success": True, "assigned_to": user_id, "model": model, "res_id": res_id}
    except Exception as e:
        return {"success": False, "error": str(e)}


@mcp.tool(description="Star/unstar a message for quick access")
def toggle_message_star(
    ctx: Context,
    message_id: int,
    starred: bool = None,
) -> Dict[str, Any]:
    """
    Star or unstar a message for the current user.
    Starred messages appear in a special "Starred" view for quick access.

    Parameters:
        message_id: ID of the message to star/unstar
        starred: True to star, False to unstar, None to toggle

    Returns:
        Dictionary containing:
        - success: Boolean indicating success
        - starred: New starred state
        - error: Error message (if failure)
    """
    odoo = ctx.request_context.lifespan_context.odoo
    try:
        if starred is None:
            # Toggle: first check current state
            message = odoo.read_records("mail.message", [message_id], fields=["starred"])
            if message:
                starred = not message[0].get("starred", False)
            else:
                return {"success": False, "error": "Message not found"}

        if starred:
            odoo.execute_method("mail.message", "set_starred", [message_id])
        else:
            odoo.execute_method("mail.message", "set_unstarred", [message_id])

        return {"success": True, "message_id": message_id, "starred": starred}
    except Exception as e:
        return {"success": False, "error": str(e)}


@mcp.tool(description="Get starred messages for the current user")
def get_starred_messages(
    ctx: Context,
    limit: int = 50,
) -> Dict[str, Any]:
    """
    Get all starred messages for the current user.

    Parameters:
        limit: Maximum number of messages to return

    Returns:
        Dictionary containing:
        - success: Boolean indicating success
        - messages: List of starred messages
        - count: Total number of starred messages
        - error: Error message (if failure)
    """
    odoo = ctx.request_context.lifespan_context.odoo
    try:
        # Get starred messages for current user
        domain = [["starred", "=", True]]

        count = odoo.execute_method("mail.message", "search_count", domain)
        messages = odoo.search_read(
            "mail.message",
            domain,
            fields=[
                "id",
                "date",
                "model",
                "res_id",
                "author_id",
                "body",
                "subject",
                "message_type",
            ],
            limit=limit,
            order="date desc",
        )

        return {"success": True, "messages": messages, "count": count}
    except Exception as e:
        return {"success": False, "error": str(e)}


@mcp.tool(description="Get users available for assignment")
def get_assignable_users(
    ctx: Context,
    model: str = None,
    search: str = None,
    limit: int = 50,
) -> Dict[str, Any]:
    """
    Get users that can be assigned to records/activities.

    Parameters:
        model: Optionally filter users who have access to this model
        search: Search term to filter users by name/email
        limit: Maximum number of users to return

    Returns:
        Dictionary containing:
        - success: Boolean indicating success
        - users: List of users with basic info
        - error: Error message (if failure)
    """
    odoo = ctx.request_context.lifespan_context.odoo
    try:
        domain = [["active", "=", True], ["share", "=", False]]  # Only internal users

        if search:
            domain.append("|")
            domain.append(["name", "ilike", search])
            domain.append(["login", "ilike", search])

        users = odoo.search_read(
            "res.users",
            domain,
            fields=["id", "name", "login", "email", "partner_id", "company_id"],
            limit=limit,
            order="name asc",
        )

        return {"success": True, "users": users, "count": len(users)}
    except Exception as e:
        return {"success": False, "error": str(e)}


@mcp.tool(description="Bulk assign activities to a user")
def bulk_delegate_activities(
    ctx: Context,
    activity_ids: List[int],
    user_id: int,
    note: str = None,
) -> Dict[str, Any]:
    """
    Delegate multiple activities to a user at once.

    Parameters:
        activity_ids: List of activity IDs to delegate
        user_id: ID of the user to delegate all activities to
        note: Optional note explaining the delegation

    Returns:
        Dictionary containing:
        - success: Boolean indicating success
        - delegated_count: Number of activities delegated
        - delegated_to: User ID the activities were delegated to
        - error: Error message (if failure)
    """
    odoo = ctx.request_context.lifespan_context.odoo
    try:
        values = {"user_id": user_id}
        odoo.execute_method("mail.activity", "write", activity_ids, values)

        # Get user name for the message
        user = odoo.read_records("res.users", [user_id], fields=["name"])
        user_name = user[0]["name"] if user else f"User {user_id}"

        if note:
            # Post notes on all affected records
            activities = odoo.read_records(
                "mail.activity", activity_ids, fields=["res_model", "res_id"]
            )
            for activity in activities:
                model = activity.get("res_model")
                res_id = activity.get("res_id")
                if model and res_id:
                    odoo.execute_method(
                        model,
                        "message_post",
                        [res_id],
                        body=f"<p>Activity delegated to <strong>{user_name}</strong>: {note}</p>",
                        message_type="comment",
                        subtype_xmlid="mail.mt_note",
                    )

        return {
            "success": True,
            "delegated_count": len(activity_ids),
            "delegated_to": user_id,
            "delegated_to_name": user_name,
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


# ----- MCP Tools: Legacy (kept for backwards compatibility) -----


@mcp.tool(description="Post a message on a record's chatter (legacy - use post_comment or post_internal_note)")
def post_message(
    ctx: Context,
    model: str,
    res_id: int,
    body: str,
    message_type: str = "comment",
    subtype_xmlid: str = "mail.mt_comment",
) -> Dict[str, Any]:
    """
    Post a message on a record's chatter (activity feed).
    Note: Consider using post_comment() for public messages or post_internal_note() for internal notes.

    Parameters:
        model: The model name (e.g., 'sale.order')
        res_id: The record ID
        body: HTML content of the message
        message_type: Type of message ('comment', 'notification', 'email')
        subtype_xmlid: Subtype XML ID ('mail.mt_comment', 'mail.mt_note')

    Returns:
        Dictionary containing:
        - success: Boolean indicating success
        - message_id: ID of the created message
        - error: Error message (if failure)
    """
    odoo = ctx.request_context.lifespan_context.odoo
    try:
        message_id = odoo.execute_method(
            model,
            "message_post",
            [res_id],
            body=body,
            message_type=message_type,
            subtype_xmlid=subtype_xmlid,
        )
        return {"success": True, "message_id": message_id}
    except Exception as e:
        return {"success": False, "error": str(e)}


# ----- MCP Tools: Legacy/Generic -----


@mcp.tool(description="Execute a custom method on an Odoo model")
def execute_method(
    ctx: Context,
    model: str,
    method: str,
    args: List = None,
    kwargs: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Execute a custom method on an Odoo model

    Parameters:
        model: The model name (e.g., 'res.partner')
        method: Method name to execute
        args: Positional arguments
        kwargs: Keyword arguments

    Returns:
        Dictionary containing:
        - success: Boolean indicating success
        - result: Result of the method (if success)
        - error: Error message (if failure)
    """
    odoo = ctx.request_context.lifespan_context.odoo
    try:
        args = args or []
        kwargs = kwargs or {}

        # Special handling for search methods like search, search_count, search_read
        search_methods = ["search", "search_count", "search_read"]
        if method in search_methods and args:
            # Search methods usually have domain as the first parameter
            # args: [[domain], limit, offset, ...] or [domain, limit, offset, ...]
            normalized_args = list(
                args
            )  # Create a copy to avoid affecting the original args

            if len(normalized_args) > 0:
                # Process domain in args[0]
                domain = normalized_args[0]
                domain_list = []

                # Check if domain is wrapped unnecessarily ([domain] instead of domain)
                if (
                    isinstance(domain, list)
                    and len(domain) == 1
                    and isinstance(domain[0], list)
                ):
                    # Case [[domain]] - unwrap to [domain]
                    domain = domain[0]

                # Normalize domain similar to search_records function
                if domain is None:
                    domain_list = []
                elif isinstance(domain, dict):
                    if "conditions" in domain:
                        # Object format
                        conditions = domain.get("conditions", [])
                        domain_list = []
                        for cond in conditions:
                            if isinstance(cond, dict) and all(
                                k in cond for k in ["field", "operator", "value"]
                            ):
                                domain_list.append(
                                    [cond["field"], cond["operator"], cond["value"]]
                                )
                elif isinstance(domain, list):
                    # List format
                    if not domain:
                        domain_list = []
                    elif all(isinstance(item, list) for item in domain) or any(
                        item in ["&", "|", "!"] for item in domain
                    ):
                        domain_list = domain
                    elif len(domain) >= 3 and isinstance(domain[0], str):
                        # Case [field, operator, value] (not [[field, operator, value]])
                        domain_list = [domain]
                elif isinstance(domain, str):
                    # String format (JSON)
                    try:
                        parsed_domain = json.loads(domain)
                        if (
                            isinstance(parsed_domain, dict)
                            and "conditions" in parsed_domain
                        ):
                            conditions = parsed_domain.get("conditions", [])
                            domain_list = []
                            for cond in conditions:
                                if isinstance(cond, dict) and all(
                                    k in cond for k in ["field", "operator", "value"]
                                ):
                                    domain_list.append(
                                        [cond["field"], cond["operator"], cond["value"]]
                                    )
                        elif isinstance(parsed_domain, list):
                            domain_list = parsed_domain
                    except json.JSONDecodeError:
                        try:
                            import ast

                            parsed_domain = ast.literal_eval(domain)
                            if isinstance(parsed_domain, list):
                                domain_list = parsed_domain
                        except:
                            domain_list = []

                # Xác thực domain_list
                if domain_list:
                    valid_conditions = []
                    for cond in domain_list:
                        if isinstance(cond, str) and cond in ["&", "|", "!"]:
                            valid_conditions.append(cond)
                            continue

                        if (
                            isinstance(cond, list)
                            and len(cond) == 3
                            and isinstance(cond[0], str)
                            and isinstance(cond[1], str)
                        ):
                            valid_conditions.append(cond)

                    domain_list = valid_conditions

                # Cập nhật args với domain đã chuẩn hóa
                normalized_args[0] = domain_list
                args = normalized_args

                # Log for debugging
                print(f"Executing {method} with normalized domain: {domain_list}")

        result = odoo.execute_method(model, method, *args, **kwargs)
        return {"success": True, "result": result}
    except Exception as e:
        return {"success": False, "error": str(e)}


@mcp.tool(description="Search for employees by name")
def search_employee(
    ctx: Context,
    name: str,
    limit: int = 20,
) -> SearchEmployeeResponse:
    """
    Search for employees by name using Odoo's name_search method.

    Parameters:
        name: The name (or part of the name) to search for.
        limit: The maximum number of results to return (default 20).

    Returns:
        SearchEmployeeResponse containing results or error information.
    """
    odoo = ctx.request_context.lifespan_context.odoo
    model = "hr.employee"
    method = "name_search"

    args = []
    kwargs = {"name": name, "limit": limit}

    try:
        result = odoo.execute_method(model, method, *args, **kwargs)
        parsed_result = [
            EmployeeSearchResult(id=item[0], name=item[1]) for item in result
        ]
        return SearchEmployeeResponse(success=True, result=parsed_result)
    except Exception as e:
        return SearchEmployeeResponse(success=False, error=str(e))


@mcp.tool(description="Search for holidays within a date range")
def search_holidays(
    ctx: Context,
    start_date: str,
    end_date: str,
    employee_id: Optional[int] = None,
) -> SearchHolidaysResponse:
    """
    Searches for holidays within a specified date range.

    Parameters:
        start_date: Start date in YYYY-MM-DD format.
        end_date: End date in YYYY-MM-DD format.
        employee_id: Optional employee ID to filter holidays.

    Returns:
        SearchHolidaysResponse:  Object containing the search results.
    """
    odoo = ctx.request_context.lifespan_context.odoo

    # Validate date format using datetime
    try:
        datetime.strptime(start_date, "%Y-%m-%d")
    except ValueError:
        return SearchHolidaysResponse(
            success=False, error="Invalid start_date format. Use YYYY-MM-DD."
        )
    try:
        datetime.strptime(end_date, "%Y-%m-%d")
    except ValueError:
        return SearchHolidaysResponse(
            success=False, error="Invalid end_date format. Use YYYY-MM-DD."
        )

    # Calculate adjusted start_date (subtract one day)
    start_date_dt = datetime.strptime(start_date, "%Y-%m-%d")
    adjusted_start_date_dt = start_date_dt - timedelta(days=1)
    adjusted_start_date = adjusted_start_date_dt.strftime("%Y-%m-%d")

    # Build the domain
    domain = [
        "&",
        ["start_datetime", "<=", f"{end_date} 22:59:59"],
        # Use adjusted date
        ["stop_datetime", ">=", f"{adjusted_start_date} 23:00:00"],
    ]
    if employee_id:
        domain.append(
            ["employee_id", "=", employee_id],
        )

    try:
        holidays = odoo.search_read(
            model_name="hr.leave.report.calendar",
            domain=domain,
        )
        parsed_holidays = [Holiday(**holiday) for holiday in holidays]
        return SearchHolidaysResponse(success=True, result=parsed_holidays)

    except Exception as e:
        return SearchHolidaysResponse(success=False, error=str(e))
