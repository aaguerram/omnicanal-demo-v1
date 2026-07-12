import os
from fpdf import FPDF

def create_dummy_pdf():
    # Asegurarnos de que el directorio existe
    pdf_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "pdf_productos")
    os.makedirs(pdf_dir, exist_ok=True)
    
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("helvetica", size=12)
    
    pdf.cell(200, 10, txt="Manual de Crema Hidratante Piel Sana", ln=1, align='C')
    
    content = """
Este producto es una crema hidratante profunda ideal para piel seca y sensible.

Ingredientes principales:
- Acido hialuronico: Retiene la humedad.
- Niacinamida: Reduce rojeces e irritacion.
- Ceramidas: Restaura la barrera cutanea.

Modo de uso:
Aplicar una capa fina sobre el rostro limpio y seco dos veces al dia, por la manana y por la noche.
Evitar el contacto directo con los ojos.

Recomendado para:
Pacientes con eccema, descamacion, y piel irritada.
No recomendado para piel extremadamente grasa con tendencia acneica severa.
"""
    pdf.multi_cell(0, 10, txt=content)
    
    file_path = os.path.join(pdf_dir, "crema_hidratante.pdf")
    pdf.output(file_path)
    print(f"PDF creado exitosamente en: {file_path}")

if __name__ == "__main__":
    create_dummy_pdf()
