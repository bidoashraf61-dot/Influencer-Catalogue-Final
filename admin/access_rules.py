"""The one decision the gate makes (docs/SAAS-MODEL.md): given the company's level for a module, whether HelloVoice
paused it, the person's role and the HTTP method, may this request go on? No imports, so it is tested on its own.

Returns None to let the request through, or the refusal code the browser and the app act on:
  locked     the company does not own the module: the locked product page, Request this module
  paused     HelloVoice switched it off for the company: "paused, your data is safe"
  no_role    the company owns it but this person has no role: Request access
  read_only  the person is a viewer and the request would change something
"""

ROLES = ("none", "viewer", "editor", "admin")
SAFE_METHODS = ("GET", "HEAD", "OPTIONS")


def refusal(level, paused, role, method):
    if level == "off":
        return "paused" if paused else "locked"
    if role == "none":
        return "no_role"
    if role == "viewer" and (method or "GET").upper() not in SAFE_METHODS:
        return "read_only"
    return None


def company_code(own_code_id, company_code_id):
    """The code a person's data lives under: their company's when they were invited into one, else their own."""
    return company_code_id if company_code_id else own_code_id


def default_role(is_colleague):
    """A person with no role row. The holder of an account is admin of their own company, as they have always
    been; a colleague invited into a company has no access until somebody gives them a role."""
    return "none" if is_colleague else "admin"
