# React Native — Component & Performance Patterns

## Optimized FlatList

```typescript
const renderItem = useCallback(({ item }: { item: Product }) => (
  <ProductCard product={item} onPress={handlePress} />
), [handlePress]);

<FlatList
  data={products}
  renderItem={renderItem}
  keyExtractor={(item) => item.id}
  getItemLayout={(_, index) => ({
    length: ITEM_HEIGHT,
    offset: ITEM_HEIGHT * index,
    index,
  })}
  removeClippedSubviews
  maxToRenderPerBatch={10}
  windowSize={5}
/>
```

## Memoized Component

```typescript
const ProductCard = React.memo<{ product: Product; onPress: (id: string) => void }>(
  ({ product, onPress }) => {
    return (
      <Pressable onPress={() => onPress(product.id)} style={styles.card}>
        <FastImage source={{ uri: product.image }} style={styles.image} />
        <Text style={styles.title}>{product.name}</Text>
      </Pressable>
    );
  },
  (prev, next) => prev.product.id === next.product.id
);
```

## Platform-Specific

```typescript
const styles = StyleSheet.create({
  shadow: Platform.select({
    ios: { shadowColor: '#000', shadowOffset: { width: 0, height: 2 }, shadowOpacity: 0.1 },
    android: { elevation: 4 },
  }),
});
```
