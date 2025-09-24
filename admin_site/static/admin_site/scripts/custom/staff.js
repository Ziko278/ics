$(document).ready(function(){
    initial_section = $('#id_section').val()
    initial_position = $('#id_position').val()
    if(initial_section==''){
        $('#id_position').html("<option value=''>----------</option>")
    }else{
        current_options = ''
        if(initial_section=='a'){
            for(const key in academic_positions){
                if(key==initial_position){
                    current_options += "<option selected='selected'>" + academic_positions[key]+ "</option>"
                }else{
                    current_options += "<option>" + academic_positions[key]+ "</option>"
                }
            }
        }else if(initial_section=='n'){
            for(const key in non_academic_positions){
                if(key==initial_position){
                    current_options += "<option selected='selected' value='"+non_academic_positions[key]+"'>" + non_academic_positions[key]+ "</option>"
                }else{
                    current_options += "<option value='"+non_academic_positions[key]+"'>" + non_academic_positions[key]+ "</option>"
                }
            }
        }
        $('#id_position').html(current_options)
    }


    $('#id_section').change(function(){
        selected_section = $(this).val()
        current_options = ''
        if(selected_section=='a'){
            for(const key in academic_positions){
                current_options += "<option>" + academic_positions[key]+ "</option>"
            }
        }else if(selected_section=='n'){
            for(const key in non_academic_positions){
                current_options += "<option value='"+non_academic_positions[key]+"'>" + non_academic_positions[key]+ "</option>"
            }
        }else{
            current_options += "<option value=''>----------</option>"
        }
        $('#id_position').html(current_options)
    })
})

academic_positions = {
    '': '---------',
    'TEACHER': 'TEACHER',
    'LAB ATTENDANT': 'LAB ATTENDANT',
    'PSYCHOLOGIST': 'PSYCHOLOGIST',
    'NANNY': 'NANNY',
    'OTHERS': 'OTHERS',
}

non_academic_positions = {
    '': '---------',
    'PRINCIPAL': 'PRINCIPAL',
    'VICE PRINCIPAL ACADEMIC': 'VICE PRINCIPAL ACADEMIC',
    'VICE PRINCIPAL ADMINISTRATION': 'VICE PRINCIPAL ADMINISTRATION',
    'DIRECTOR': 'DIRECTOR',
    'PROPRIETOR': 'PROPRIETOR',
    'ACCOUNTANT': 'ACCOUNTANT',
    'BURSARY': 'BURSARY',
    'REGISTRAR': 'REGISTRAR',
    'RECEPTIONIST': 'RECEPTIONIST',
    'ICT': 'ICT',
    'CHIEF SECURITY OFFICER': 'CHIEF SECURITY OFFICER',
    'SECURITY OFFICER': 'SECURITY OFFICER',
    'CHEF': 'CHEF',
    'OTHERS': 'OTHERS',

}