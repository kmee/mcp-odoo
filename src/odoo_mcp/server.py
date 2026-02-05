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


@mcp.tool(description="Post a message on a record's chatter")
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


@mcp.tool(description="Get messages/chatter history for a record")
def get_messages(
    ctx: Context,
    model: str,
    res_id: int,
    limit: int = 20,
) -> Dict[str, Any]:
    """
    Get the message history (chatter) for a record.

    Parameters:
        model: The model name (e.g., 'sale.order')
        res_id: The record ID
        limit: Maximum number of messages to return

    Returns:
        Dictionary containing:
        - success: Boolean indicating success
        - messages: List of messages
        - error: Error message (if failure)
    """
    odoo = ctx.request_context.lifespan_context.odoo
    try:
        messages = odoo.search_read(
            "mail.message",
            [["model", "=", model], ["res_id", "=", res_id]],
            fields=["id", "date", "author_id", "body", "message_type", "subtype_id"],
            limit=limit,
            order="date desc",
        )
        return {"success": True, "messages": messages}
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
