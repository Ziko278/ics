$(document).ready(function(){
    $('#parent_detail_div').hide()
    parent_list = $('#parent_list').val()
    parent_list = JSON.parse(parent_list)
    parent_name_list = {}
    for(const key in parent_list){
        if(parent_list[key]['fields']['middle_name'] == null){
            parent_name_list[parent_list[key]['pk']] = parent_list[key]['fields']['surname'] + " " + parent_list[key]['fields']['last_name']
            parent_name_list[parent_list[key]['pk']] = parent_name_list[parent_list[key]['pk']].toLowerCase()
        }else{
            parent_name_list[parent_list[key]['pk']] = parent_list[key]['fields']['surname'] + " " + parent_list[key]['fields']['middle_name'] + " " + parent_list[key]['fields']['last_name']
            parent_name_list[parent_list[key]['pk']] = parent_name_list[parent_list[key]['pk']].toLowerCase()
        }
    }

    $('#parent_search').keyup(function(){

        parent_detail_list = ''
        search_value = $(this).val().toLowerCase()
        search_value_array = search_value.split(" ")

        if(search_value==''){
            $('#parent_detail_div').fadeOut()
        }else{
            for(const key in parent_name_list){
                parent_search_result = true
                for(const search_key in search_value_array){
                    if(!parent_name_list[key].includes(search_value_array[search_key])){
                        parent_search_result = false
                    }
                }
                if(parent_search_result==true){
                    parent_detail_list += "<li style='display:block;margin-bottom:2px;' class='btn btn-info select_parent' parent_id="+key+">"+ parent_name_list[key].toUpperCase() +"</li>"
                }
            }

            if(parent_detail_list == ''){
                    parent_detail_list += "<li style='display:block;margin-bottom:2px;' class='btn btn-info select_parent'>No Parent Found for Search Query</li>"
            }
        }

        $('#parent_detail_list').html(parent_detail_list)
    })

    $(document).on('click','.select_parent', function(){
        parent_id = $(this).attr('parent_id')
        parent_fullname = parent_name_list[parent_id]
        $('#parent_fullname').text(parent_fullname.toUpperCase())

        for(const key in parent_list){
            if(parent_list[key]['pk'] == parent_id){
                parent_full_detail = parent_list[key]['fields']
            }
        }
        parent_mobile = parent_full_detail['mobile']
        if(parent_mobile == null){
            parent_mobile = 'Mobile Not Provided'
        }
        $('#parent_mobile').text(parent_mobile)

        parent_email = parent_full_detail['email']
        if(parent_email == null){
            parent_email = 'Email Not Provided'
        }
        $('#parent_email').text(parent_email)

        parent_address = parent_full_detail['residential_address']
        if(parent_address == null){
            parent_address = 'Address Not Provided'
        }
        $('#parent_address').text(parent_address)

        parent_image = parent_full_detail['image']
        parent_image_src = '/media/' + parent_image
        if(parent_image == null || parent_image==''){
            $('#parent_image').hide()
            $('#default_image').show()
        }else{
            parent_image = "<img style='width:100px;height:100px;border-radius:5px;' src='"+parent_image_src+"' />"
            $('#parent_image').html(parent_image)
            $('#parent_image').show()
            $('#default_image').hide()
        }

        proceed_button_href =  parent_id + "/register"
        $('#proceed_button').attr('href', proceed_button_href)

        $('#parent_detail_div').fadeIn()

    })
})
