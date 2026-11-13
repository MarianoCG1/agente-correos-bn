"""Nombres con los que aparece cada columna en los Excel del banco (heredado de v1).

El cronograma cambia de forma entre campañas; por eso cada campo tiene alias.
Los alias con '.1' o '.2' existen porque pandas renombra así las columnas repetidas.
"""

COLUMNAS_REQUERIDAS = {
    "Agencia": ["Agencia", "AGENCIA", "Ag.", "Agency", "BN Agencia", "Agencia BN", "Sede", "AA", "AG"],
    "Departamento": ["Departamento", "DEPARTAMENTO", "Dpto", "Depto", "DD", "DEP"],
    "Provincia": ["Provincia", "PROVINCIA", "Prov", "PP", "PROV"],
    "Distrito": ["Distrito", "DISTRITO", "Dist", "dd", "DIST"],
    "Punto_de_Pago": ["Punto de Pago", "Punto_de_Pago", "PUNTO DE PAGO", "Pto Pago", "pp", "PPP"],
    "Fecha_Pago": ["Fecha Pago", "Fecha_Pago", "FECHA PAGO", "Fec. Pago", "Fecha\nPropuesta",
                   "Fecha Propuesta", "Fecha Propuesta "],
    "P65_Usuarios": ["P65 Usuarios", "P65_Usuarios", "N° Usuarios P65", "Usuarios P65", "N° Usuarios", "U_P65"],
    "P65_Importe": ["P65 Importe", "P65_Importe", "Importe P65", "Imp. P65", "Importe", "I_P65"],
}

COLUMNAS_OPCIONALES = {
    "Juntos_Usuarios": ["Juntos Usuarios", "N° Usuarios Juntos", "Usuarios Juntos", "N° Usuarios.1", "U_JUNTOS"],
    "Juntos_Importe": ["Juntos Importe", "Importe Juntos", "Imp. Juntos", "Importe.1", "I_JUNTOS"],
    "Contigo_Usuarios": ["Contigo Usuarios", "N° Usuarios Contigo", "Usuarios Contigo", "N° Usuarios.2", "U_CONTIGO"],
    "Contigo_Importe": ["Contigo Importe", "Importe Contigo", "Imp. Contigo", "Importe.2", "I_CONTIGO"],
    "ETV": ["ETV", "E.T.V.", "Etv", "EMPRESA"],
    "Hora_Pago": ["Hora Pago", "Hora_Pago", "Hr. Pago", "Hora", "HR"],
    "Fecha_Entrega": ["Fecha Entrega", "Fecha_Entrega", "Fec. Entrega", "FECHA", "FEC_ENT", "Fecha"],
    "Hora_Entrega": ["Hora Entrega", "Hora_Entrega", "Hr. Entrega", "Hora.1", "HR_ENT"],
    "Cod_Pueblo": ["Cod Pueblo", "Código Pueblo", "Cod. Pueblo", "cp", "C_PUEBLO"],
    "Cod_Pto_Pago": ["Cod Pto Pago", "Código Pto Pago", "Cod. Pto. Pago", "Cod. Pto Pago", "cpp", "C_PTO"],
}

HOJAS_PREFERIDAS = ("CRONOGRAMA", "ETV", "PAGOS", "PROGRAMA")

PALABRAS_ENCABEZADO = ("agencia", "departamento", "provincia", "fecha", "usuarios", "distrito", "importe")

# Columnas de la lista de agencias (agencias_correos.xlsx)
ALIAS_AGENCIA = ["Agencia", "AGENCIA", "AGENCIAS", "Agencias", "Ag.", "Agency", "BN Agencia",
                 "Agencia BN", "Sede", "AA", "AG"]
ALIAS_CORREO = ["Correo", "Email", "E-mail", "Mail", "E-mail BN", "E_MAIL",
                "JEFE DE PAGO", "Jefe de Pago", "Jefe De Pago"]
ALIAS_CC = ["CC", "Copia", "C.C.", "Cco", "CCO", "ADMINISTRADOR", "Administrador"]
