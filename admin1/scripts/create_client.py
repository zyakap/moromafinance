def create_client(request):
    if request.method == 'POST':
        if request.POST.get('limit'):
            limit = request.POST.get('limit')
            intlimit = int(limit)
            user.repayment_limit = intlimit
            user.save()
    