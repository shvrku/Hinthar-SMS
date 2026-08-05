from rest_framework.pagination import PageNumberPagination


class StandardPageNumberPagination(PageNumberPagination):
    """
    Default list pagination: 50 per page, client may raise up to 200 via ?page_size=.
    """
    page_size = 50
    page_size_query_param = 'page_size'
    max_page_size = 200
    page_query_param = 'page'
