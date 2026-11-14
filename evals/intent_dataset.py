"""Evaluation dataset: what a customer says -> which intent the agent should pick.

Each case is a dict with:
    id        short identifier, used in the report when a case fails
    message   what the customer writes, in their own words
    expected  one of: no_service | slow_internet | intermittent | wifi |
                      wifi_password | out_of_scope
    note      (optional) why this case is tricky

Write the messages the way real people write them: lowercase, typos, slang,
vague descriptions. The point is to find where the agent breaks, not to make
it look good.
"""

CASES = [
    # --- no_service: no internet at all --------------------------------------
    {"id": "ns-easy", "message": "no tengo internet", "expected": "no_service"},
    {"id": "ns-slang", "message": "se me cayo todo, no anda nada desde anoche",
     "expected": "no_service", "note": "no usa la palabra internet"},

    # --- slow_internet -------------------------------------------------------
    {"id": "sl-easy", "message": "el internet anda muy lento", "expected": "slow_internet"},
    {"id": "sl-netflix", "message": "no puedo ver netflix, se queda cargando todo el tiempo",
     "expected": "slow_internet", "note": "describe el sintoma, no la causa"},

    # --- wifi ----------------------------------------------------------------
    {"id": "wf-no-red", "message": "mi celu no me encuentra la red wifi", "expected": "wifi"},

    # --- out_of_scope --------------------------------------------------------
    {"id": "oos-factura", "message": "queria consultar por la factura de este mes",
     "expected": "out_of_scope"},

         {"id": "in-01", "message": "se me corta cada 10 minutos y vuelve solo", "expected": "intermittent"},

    # --- intermittent: se corta y vuelve solo ---------------------------------
    {"id": "in-02", "message": "tengo microcortes constantes, se me va y viene a cada rato",
     "expected": "intermittent"},
    {"id": "in-03", "message": "se me apaga el modem y vuelve a prender, es todo el tiempo",
     "expected": "intermittent"},
    {"id": "in-04", "message": "se corta la conexion y a los minutos vuelve sola",
     "expected": "intermittent"},
    {"id": "in-mixto", "message": "anda lento y ademas a veces se corta",
     "expected": "intermittent", "note": "DISCUTIBLE: mezcla lentitud e intermitencia"},

    # --- wifi: no ve la red, no conecta, no llega ----------------------------
    {"id": "wf-ningun-disp", "message": "no me sale la red wifi mia en ningun dispositivo",
     "expected": "wifi", "note": "suele ser bandsteering: equipos viejos no ven la de 5 GHz"},
    {"id": "wf-auth", "message": "me sale error de autenticacion cuando quiero entrar al wifi",
     "expected": "wifi"},
    {"id": "wf-sin-internet", "message": "me conecta pero me dice conectado sin internet",
     "expected": "wifi", "note": "DISCUTIBLE: suena a sin servicio, pero suele resolverse cambiando la clave"},
    {"id": "wf-cobertura", "message": "tengo un piso arriba y no llega la señal, no cargan los videos",
     "expected": "wifi", "note": "DISCUTIBLE: dice videos y señal, pero es cobertura de wifi"},

    # --- wifi_password: quiere cambiar la clave ------------------------------
    {"id": "wp-01", "message": "necesito cambiar la contraseña de mi red wifi",
     "expected": "wifi_password"},
    {"id": "wp-02", "message": "quiero cambiar la clave de wifi", "expected": "wifi_password"},
    {"id": "wp-03", "message": "le di la clave a un vecino y ahora quiero ponerle otra",
     "expected": "wifi_password"},
    {"id": "wp-olvido", "message": "me olvide la clave del wifi y quiero poner una nueva",
     "expected": "wifi_password", "note": "DISCUTIBLE: olvido de clave vs. pedido de cambio"},

    # --- no_service: no tiene nada -------------------------------------------
    {"id": "ns-nada", "message": "no tengo señal, el modem esta prendido pero no tengo nada de internet",
     "expected": "no_service"},
    {"id": "ns-vago", "message": "no funciona el internet", "expected": "no_service",
     "note": "vago: el diagnostico decide despues si es la linea o su dispositivo"},
    {"id": "ns-dice-wifi", "message": "se me corto el wifi y no tengo nada en ningun dispositivo",
     "expected": "no_service", "note": "ENGAÑOSO: dice wifi pero no tiene servicio"},

    # --- slow_internet -------------------------------------------------------
    {"id": "sl-lag", "message": "tengo mucho lag jugando online", "expected": "slow_internet"},
    {"id": "sl-videos", "message": "no me cargan los videos en ninguna parte de la casa",
     "expected": "slow_internet", "note": "en toda la casa: no es cobertura de wifi"},
    {"id": "sl-typo", "message": "el inteenet me anda re lentoo dsde ayer", "expected": "slow_internet",
     "note": "errores de tipeo"},

    # --- out_of_scope --------------------------------------------------------
    {"id": "oos-cobertura", "message": "queria saber si tienen cobertura en mi barrio para contratar",
     "expected": "out_of_scope", "note": "comercial: venta, no soporte"},
    {"id": "oos-baja", "message": "quiero dar de baja el servicio", "expected": "out_of_scope"},
    {"id": "oos-mudanza", "message": "me mudo el mes que viene y necesito el cambio de domicilio",
     "expected": "out_of_scope"},
    {"id": "oos-megas", "message": "quiero pasarme a un plan de mas megas",
     "expected": "out_of_scope", "note": "comercial: cambio de plan"},
    {"id": "oos-corpo", "message": "llamo por la conexion de la empresa, tenemos un plan corporativo",
     "expected": "out_of_scope", "note": "tecnica corporativa no es L1 residencial"},
]


def by_intent() -> dict[str, int]:
    """How many cases per intent, to check the dataset is balanced."""
    counts: dict[str, int] = {}
    for case in CASES:
        counts[case["expected"]] = counts.get(case["expected"], 0) + 1
    return dict(sorted(counts.items()))


if __name__ == "__main__":
    print(f"{len(CASES)} casos")
    for intent, count in by_intent().items():
        print(f"  {count:>3}  {intent}")
