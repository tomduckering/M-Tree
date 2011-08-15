from collections import namedtuple
import functions
from heap_queue import HeapQueue



_CHECKED = True
if _CHECKED:
	def _checked(unchecked_method):
		def checked_method(mtree, *args, **kwargs):
			result = unchecked_method(mtree, *args, **kwargs)
			mtree._check()
			return result
		return checked_method
else:
	def _checked(unchecked_method):
		return unchecked_method



_INFINITY = float("inf")

_ItemWithDistances = namedtuple('_ItemWithDistances', 'item, distance, min_distance')



class _RootNodeReplacement(Exception):
	def __init__(self, new_root):
		super(_RootNodeReplacement, self).__init__(new_root)
		self.new_root = new_root

class _SplitNodeReplacement(Exception):
	def __init__(self, new_nodes):
		super(_SplitNodeReplacement, self).__init__(new_nodes)
		self.new_nodes = new_nodes

class _NodeUnderCapacity(Exception):
	pass


class _IndexItem(object):
	
	def __init__(self, data):
		self.data = data
		self.radius = 0                  # Updated when a child is added to this item
		self.distance_to_parent = None   # Updated when this item is added to a parent
	
	def _check(self, mtree):
		self._check_data()
		self._check_radius()
		self._check_distance_to_parent()
	
	def _check_data(self):
		assert self.data is not None
	
	def _check_radius(self):
		assert self.radius is not None
		assert self.radius >= 0
	
	def _check_distance_to_parent(self):
		assert not isinstance(self, (_RootLeafNode, _RootNode)), self
		assert self.distance_to_parent is not None
		assert self.distance_to_parent >= 0
	
	def _check_distance_to_parent__root(self):
		assert isinstance(self, (_RootLeafNode, _RootNode)), self
		assert self.distance_to_parent is None



class _Node(_IndexItem):
	
	def __init__(self, data):
		super(_Node, self).__init__(data)
		self.children = []
	
	def add_data(self, data, distance, mtree):
		child = self.do_add_data(data)
		self.update_metrics(child, distance)
		
		if len(self.children) > mtree.max_node_capacity:
			data_objects = frozenset(child.data for child in self.children)
			cached_distance_function = functions.make_cached_distance_function(mtree.distance_function)
			
			(promoted_data1, partition1,
			 promoted_data2, partition2) = mtree.split_function(data_objects, cached_distance_function)
			
			split_node_replacement_class = self.get_split_node_replacement_class()
			new_nodes = []
			for promoted_data, partition in [(promoted_data1, partition1),
			                                 (promoted_data2, partition2)]:
				new_node = split_node_replacement_class(promoted_data)
				for data in partition:
					child = self.get_child_by_data(data)
					distance = cached_distance_function(promoted_data, data)
					new_node.add_child(child, distance)
				new_nodes.append(new_node)
			
			raise _SplitNodeReplacement(new_nodes)
	
	
	def do_add_data__leaf(self, data):
		entry = _Entry(data)
		self.children.append(entry)
		return entry
	
	def get_split_node_replacement_class__leaf(self):
		return _LeafNode
	
	def add_child(self, child, distance):
		self.children.append(child)
		self.update_metrics(child, distance)
	
	def remove_data(self, data, distance, mtree):
		self.do_remove_data(data, distance, mtree)
		if len(self.children) < self.get_min_capacity(mtree):
			raise _NodeUnderCapacity()
	
	def do_remove_data__leaf(self, data, distance, mtree):
		index = self.get_child_index_by_data(data)
		if index is None:
			raise KeyError("Data not found")
		else:
			del self.children[index]
	
	def do_remove_data(self, data, distance, mtree):
		assert not isinstance(self, (_RootLeafNode, _LeafNode)), self
		for child in self.children:
			if abs(distance - child.distance_to_parent) <= child.radius:   # TODO: confirm
				distance_to_child = mtree.distance_function(data, child.data)
				if distance_to_child <= child.radius:
					try:
						child.remove_data(data, distance_to_child, mtree)
					except KeyError:
						# If KeyError was raised, then the data was not found in the child
						pass
					except _NodeUnderCapacity:
						self.balance_children(child, mtree)
						return
					else:
						return
		raise KeyError("Data not found")
	
	def update_metrics(self, child, distance):
		child.distance_to_parent = distance
		self.radius = max(self.radius, distance + child.radius)
	
	def get_child_index_by_data(self, data):
		for index, child in enumerate(self.children):
			if child.data == data:
				return index
	
	def get_child_by_data(self, data):
		index = self.get_child_index_by_data(data)
		child = self.children[index]
		assert child.data == data
		return child
	
	def balance_children(self, the_child, mtree):
		# Tries to find another_child which can donate a grandchild to the_child.
		
		nearest_donor = None
		distance_nearest_donor = _INFINITY
		
		nearest_merge_candidate = None
		distance_nearest_merge_candidate = _INFINITY
		
		for another_child in (child for child in self.children if child is not the_child):
			distance = mtree.distance_function(the_child.data, another_child.data)
			if len(another_child.children) > another_child.get_min_capacity(mtree):
				if distance < distance_nearest_donor:
					distance_nearest_donor = distance
					nearest_donor = another_child
			else:
				if distance < distance_nearest_merge_candidate:
					distance_nearest_merge_candidate = distance
					nearest_merge_candidate = another_child
		
		if nearest_donor is None:
			# Merge
			for grandchild in the_child.children:
				distance = mtree.distance_function(grandchild.data, nearest_merge_candidate.data)
				nearest_merge_candidate.add_child(grandchild, distance)
			
			index = self.get_child_index_by_data(the_child.data)
			del self.children[index]
		else:
			# Donate
			raise NotImplementedError()
		
	
	def _check(self, mtree):
		super(_Node, self)._check(mtree)
		for child in self.children:
			self._check_child_class(child)
			self._check_child_metrics(child, mtree)
			child._check(mtree)
	
	def _check_child_class(self, child):
		expected_class = self._get_expected_child_class()
		assert isinstance(child, expected_class)
	
	@staticmethod
	def _get_expected_child_class__leaf(self):
		return _Entry
	
	def _check_child_metrics(self, child, mtree):
		assert child.distance_to_parent == mtree.distance_function(child.data, self.data)
		assert child.distance_to_parent + child.radius <= self.radius



class _RootLeafNode(_Node):
	
	do_add_data = _Node.do_add_data__leaf
	
	get_split_node_replacement_class = _Node.get_split_node_replacement_class__leaf
	
	def remove_data(self, data, distance, mtree):
		try:
			super(_RootLeafNode, self).remove_data(data, distance, mtree)
		except _NodeUnderCapacity:
			raise _RootNodeReplacement(None)
	
	do_remove_data = _Node.do_remove_data__leaf
	
	@staticmethod
	def get_min_capacity(mtree):
		return 1
	
	_check_distance_to_parent = _Node._check_distance_to_parent__root
	
	_get_expected_child_class = _Node._get_expected_child_class__leaf



class _RootNode(_Node):
	
	def remove_data(self, data, distance, mtree):
		try:
			super(_RootNode, self).remove_data(data, distance, mtree)
		except _NodeUnderCapacity:
			# Promote the only child to root
			(the_child,) = self.children
			if isinstance(the_child, _InternalNode):
				raise NotImplementedError()
			else:
				assert isinstance(the_child, _LeafNode)
				new_root_class = _RootLeafNode
			
			new_root = new_root_class(the_child.data)
			for grandchild in the_child.children:
				distance = mtree.distance_function(new_root.data, grandchild.data)
				new_root.add_child(grandchild, distance)
			
			raise _RootNodeReplacement(new_root)
	
	
	@staticmethod
	def get_min_capacity(mtree):
		return 2
	
	_check_distance_to_parent = _Node._check_distance_to_parent__root
	
	@staticmethod
	def _get_expected_child_class():
		return (_InternalNode, _LeafNode)


class _InternalNode(_Node):
	pass


class _LeafNode(_Node):
	
	do_remove_data = _Node.do_remove_data__leaf
	
	def get_min_capacity(self, mtree):
		return mtree.min_node_capacity
	
	_get_expected_child_class = _Node._get_expected_child_class__leaf


class _Entry(_IndexItem):
	pass



class MTreeBase(object):
	"""
	A data structure for indexing objects based on their proximity.
	
	The data objects must be any hashable object and the support functions
	(distance and split functions) must understand them.
	
	See http://en.wikipedia.org/wiki/M-tree
	"""
	
	
	ResultItem = namedtuple('ResultItem', 'data, distance')
	
	
	def __init__(self,
		         min_node_capacity=50, max_node_capacity=None,
		         distance_function=functions.euclidean_distance,
		         split_function=functions.make_split_function(functions.random_promotion, functions.balanced_partition)
		        ):
		"""
		Creates an M-Tree.
		
		The argument min_node_capacity must be at least 2.
		The argument max_node_capacity should be at least 2*min_node_capacity-1.
		The optional argument distance_function must be a function which calculates
		the distance between two data objects.
		The optional argument split_function must be a function which chooses two
		data objects and then partitions the set of data into two subsets
		according to the chosen objects. Its arguments are the set of data objects
		and the distance_function. Must return a sequence with the following four values:
			- First chosen data object.
			- Subset with at least [min_node_capacity] objects based on the first
				chosen data object. Must contain the first chosen data object.
			- Second chosen data object.
			- Subset with at least [min_node_capacity] objects based on the second
				chosen data object. Must contain the second chosen data object.
		"""
		if min_node_capacity < 2:
			raise ValueError("min_node_capacity must be at least 2")
		if max_node_capacity is None:
			max_node_capacity = 2 * min_node_capacity - 1
		if max_node_capacity <= min_node_capacity:
			raise ValueError("max_node_capacity must be greater than min_node_capacity")
		
		self.min_node_capacity = min_node_capacity
		self.max_node_capacity = max_node_capacity
		self.distance_function = distance_function
		self.split_function = split_function
		self.root = None
	
	
	@_checked
	def add(self, data):
		"""
		Adds and indexes an object.
		
		The object must not currently already be indexed!
		"""
		if self.root is None:
			self.root = _RootLeafNode(data)
			self.root.add_data(data, 0, self)
		else:
			distance = self.distance_function(data, self.root.data)
			try:
				self.root.add_data(data, distance, self)
			except _SplitNodeReplacement as e:
				assert len(e.new_nodes) == 2
				self.root = _RootNode(self.root.data)
				for new_node in e.new_nodes:
					distance = self.distance_function(self.root.data, new_node.data)
					self.root.add_child(new_node, distance)
	
	
	@_checked
	def remove(self, data):
		"""
		Removes an object from the index.
		"""
		distance_to_root = self.distance_function(data, self.root.data)
		try:
			self.root.remove_data(data, distance_to_root, self)
		except _RootNodeReplacement as e:
			self.root = e.new_root
	
	
	def get_nearest(self, query_data, range=_INFINITY, limit=_INFINITY):
		"""
		Returns an iterator on the indexed data nearest to the query_data. The
		returned items are tuples containing the data and its distance to the
		query_data, in increasing distance order. The results can be limited by
		the range (maximum distance from the query_data) and limit arguments.
		"""
		if self.root is None:
			# No indexed data!
			return
		
		distance = self.distance_function(query_data, self.root.data)
		min_distance = max(distance - self.root.radius, 0)
		
		pending_queue = HeapQueue(
				content=[_ItemWithDistances(item=self.root, distance=distance, min_distance=min_distance)],
				key=lambda iwd: iwd.min_distance,
			)
		
		nearest_queue = HeapQueue(key=lambda iwd: iwd.distance)
		
		yielded_count = 0
		
		while pending_queue:
			pending = pending_queue.pop()
			
			node = pending.item
			assert isinstance(node, _Node)
			
			for child in node.children:
				if abs(pending.distance - child.distance_to_parent) - child.radius <= range:
					child_distance = self.distance_function(query_data, child.data)
					child_min_distance = max(child_distance - child.radius, 0)
					if child_min_distance <= range:
						iwd = _ItemWithDistances(item=child, distance=child_distance, min_distance=child_min_distance)
						if isinstance(child, _Entry):
							nearest_queue.push(iwd)
						else:
							pending_queue.push(iwd)
			
			# Tries to yield known results so far
			if pending_queue:
				next_pending = pending_queue.head()
				next_pending_min_distance = next_pending.min_distance
			else:
				next_pending_min_distance = _INFINITY
			
			while nearest_queue:
				next_nearest = nearest_queue.head()
				assert isinstance(next_nearest, _ItemWithDistances)
				if next_nearest.distance <= next_pending_min_distance:
					_ = nearest_queue.pop()
					assert _ is next_nearest
					
					yield self.ResultItem(data=next_nearest.item.data, distance=next_nearest.distance)
					yielded_count += 1
					if yielded_count >= limit:
						# Limit reached
						return
				else:
					break
	
	
	def _check(self):
		if self.root is not None:
			self.root._check(self)
