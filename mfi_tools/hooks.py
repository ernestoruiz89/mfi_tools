app_name = "mfi_tools"
app_title = "MFI Tools"
app_publisher = "Ernesto Ruiz Escorcia"
app_description = "Herramienta para simplificar reporteria para instituciones de microfinanzas"
app_email = "eruiz@wbapps.com"
app_license = "mit"
app_icon = "fa fa-line-chart"
app_color = "#0f766e"
app_logo_url = "/assets/mfi_tools/images/mfi-tools.svg"
app_home = "/desk/mfi-tools/panel-mfi-tools"

required_apps = ["erpnext"]

add_to_apps_screen = [
    {
        "name": app_name,
        "logo": app_logo_url,
        "title": app_title,
        "route": app_home,
        "has_permission": "mfi_tools.check_app_permission",
        "sequence_id": 20,
    }
]

before_install = "mfi_tools.mfi_tools.utils.migrate.before_install"
